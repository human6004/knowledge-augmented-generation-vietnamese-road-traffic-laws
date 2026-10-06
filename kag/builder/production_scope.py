"""Offline production preflight. Call before constructing any vectorizer/writer."""
from collections.abc import Mapping
from collections import Counter
from dataclasses import dataclass, field
import hashlib
import ipaddress
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import SimpleNamespace
import sqlite3
import tempfile
from urllib.parse import urlsplit

from .codec import canonical_json
from .graph_plan import plan_hash
from .inputs import ARTIFACT_HASHES
from .resilient_vectorizer import TARGETS, _valid_vector


C3_IDENTITY = {
    'nodes_jsonl_sha256': '9a19e7e79a03c0ce339bf3da20d11db395c5662821178e5013d1f026fc8bea86',
    'edges_jsonl_sha256': 'd419eca20055fac50d82dd872f489e8b514fba1befd5e19a848cae38f57b715b',
    'plan_sha256': 'ee8b3709e89060b446c508f2c87bdcae7f401530976a30beecdd92935cdca917',
    'schema_sha256': 'ec05cc76303b99c43f7d2d8ed662459daeafe69fa750b7ebbdbf975fb794c23c',
    'contract_sha256': '3a57fae7702e4f063b175d58e58a53d74b991b9c52f822c8cc769770687156c0',
}
ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PROJECT_ID = 2
_PRODUCTION_PROOF = object()


class ProductionScopeError(ValueError):
    """Production preflight refused; no embedding or graph write is authorized."""


def _checksum(path):
    digest = hashlib.sha256()
    try:
        with Path(path).open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
    except OSError:
        raise ProductionScopeError('required production file cannot be read') from None
    return digest.hexdigest()


def _endpoint(value, schemes, location):
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or '').lower()
        port = parsed.port
        try:
            local = host == 'localhost' or ipaddress.ip_address(host).is_loopback
        except ValueError:
            local = False
        if (not isinstance(value, str) or parsed.scheme not in schemes or not host or not port
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in ('', '/') or value.strip() != value
                or (location == 'host' and not local)
                or (location == 'container' and local)):
            raise ValueError
    except (TypeError, ValueError, AttributeError):
        raise ProductionScopeError('endpoint must be explicit, credential-free and match runtime location') from None


@dataclass(frozen=True)
class ProductionSettings:
    scope: str = 'DENY'
    runtime_location: str | None = None
    host_addr: str | None = None
    neo4j_uri: str | None = None
    project_name: str | None = None
    namespace: str | None = None
    expected_project_id: int | None = None
    vector_dimensions: int | None = None
    confirmation: str | None = field(default=None, repr=False)

    def validate(self):
        if self.scope != 'PRODUCTION' or self.runtime_location not in ('host', 'container'):
            raise ProductionScopeError('explicit PRODUCTION scope and runtime location are required')
        if (not isinstance(self.project_name, str) or not self.project_name.strip()
                or self.project_name.strip() != self.project_name
                or self.project_name == 'VietRoadTrafficC43A10Pct'
                or self.project_name.startswith('C4_1_SMOKE_')
                or self.namespace != 'VietRoadTraffic'):
            raise ProductionScopeError('production project name/namespace must identify a separate target')
        if type(self.expected_project_id) is not int or self.expected_project_id <= 0:
            raise ProductionScopeError('expected production project ID must be a positive native int')
        if self.expected_project_id == SAMPLE_PROJECT_ID:
            raise ProductionScopeError('reserved sample project ID cannot authorize production')
        if type(self.vector_dimensions) is not int or self.vector_dimensions != 3072:
            raise ProductionScopeError('production vector dimension must be 3072')
        expected = (f'CONFIRM_PRODUCTION:{self.project_name}:{self.namespace}:'
                    f'{self.expected_project_id}:{C3_IDENTITY["plan_sha256"]}')
        if self.confirmation != expected:
            raise ProductionScopeError('explicit production confirmation must bind project identity and C3 plan')
        _endpoint(self.host_addr, ('http', 'https'), self.runtime_location)
        _endpoint(self.neo4j_uri, ('bolt', 'neo4j', 'bolt+s', 'neo4j+s'), self.runtime_location)


def _spec_hash(spec):
    return hashlib.sha256(canonical_json(spec).encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class ProductionScope:
    settings: ProductionSettings
    file_checksums: tuple[tuple[Path, str], ...]
    node_hashes: Mapping
    edge_hashes: Mapping
    contract_hash: str
    _proof: object = field(repr=False, compare=False)

    @property
    def node_keys(self):
        return self.node_hashes.keys()

    def verify_files(self, contract):
        self.settings.validate()
        if self._proof is not _PRODUCTION_PROOF or _spec_hash(contract) != self.contract_hash:
            raise ProductionScopeError('production scope/schema contract proof differs')
        # ponytail: exact rehash per batch; optimize only with immutable input snapshots in a future runner.
        for path, expected in self.file_checksums:
            if _checksum(path) != expected:
                raise ProductionScopeError(f'{path.name}: production checksum changed after preflight')

    def validate_specs(self, nodes, edges, *, require_vectors=False, complete=False):
        node_keys, edge_keys = [], []
        for spec in nodes:
            props = dict(spec['properties'])
            targets = TARGETS.get(spec['type'].rsplit('.', 1)[-1], ())
            permitted = {vector for _, vector in targets}
            for name in list(props):
                if name.startswith('_'):
                    if name not in permitted or not _valid_vector(props[name], 3072):
                        raise ProductionScopeError('production node contains an unauthorized or invalid 3072 vector')
                    props.pop(name)
            if require_vectors and any(spec['properties'].get(prop) and vector not in spec['properties']
                                       for prop, vector in targets):
                raise ProductionScopeError('production content requires its 3072 vector before writing')
            key = (spec['type'], spec['id'])
            if self.node_hashes.get(key) != _spec_hash(dict(spec, properties=props)):
                raise ProductionScopeError('production node payload differs from C3 golden plan')
            node_keys.append(key)
        for spec in edges:
            key = tuple(spec['tuple'])
            # SDK serializes JSON tuples as lists; canonical_json treats them identically.
            if self.edge_hashes.get(key) != _spec_hash(spec):
                raise ProductionScopeError('production edge payload differs from C3 golden plan')
            edge_keys.append(key)
        if len(set(node_keys)) != len(node_keys) or len(set(edge_keys)) != len(edge_keys):
            raise ProductionScopeError('production batches cannot contain duplicate identities')
        if complete and (set(node_keys) != set(self.node_hashes) or set(edge_keys) != set(self.edge_hashes)):
            raise ProductionScopeError('production staged plan must equal the complete C3 golden plan')


class _C3Index:
    """Run-owned (or temporary) SQLite storage; cache and counters stay bounded."""
    def __init__(self, db_path):
        self.temporary = tempfile.TemporaryDirectory(prefix='kag-c3-') if db_path is None else None
        self.path = Path(db_path) if db_path is not None else Path(self.temporary.name) / 'sources.sqlite3'
        if self.path.is_symlink() or self.path.resolve().is_relative_to(Path(__file__).resolve().parents[2]):
            raise ProductionScopeError('C3 index must be outside the repository')
        self.db = sqlite3.connect(self.path)
        self.db.execute('PRAGMA cache_size=-2048')
        self.db.execute('PRAGMA temp_store=FILE')
        self.db.execute('''CREATE TABLE IF NOT EXISTS c3_sources (
            kind TEXT, ordinal INTEGER, key TEXT, source_hash TEXT, payload TEXT,
            from_key TEXT, to_key TEXT, PRIMARY KEY(kind,key), UNIQUE(kind,ordinal))''')
        self.counts = {}

    def seal(self):
        self.db.close()
        self.db = sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True)
        self.db.execute('PRAGMA cache_size=-2048')
        self.db.execute('PRAGMA temp_store=FILE')

    def close(self):
        if getattr(self, 'db', None) is not None:
            self.db.close()
            self.db = None
        if self.temporary is not None:
            self.temporary.cleanup()

    def __del__(self):
        try: self.close()
        except Exception: pass


class _DiskRecords:
    def __init__(self, index, kind):
        self.index, self.kind = index, kind

    def __len__(self):
        return self.index.counts[self.kind]

    def __iter__(self):
        for (payload,) in self.index.db.execute(
                'SELECT payload FROM c3_sources WHERE kind=? ORDER BY ordinal', (self.kind,)):
            yield json.loads(payload)


class _DiskHashes(Mapping):
    def __init__(self, index, kind):
        self.index, self.kind = index, kind

    def __len__(self):
        return self.index.counts[self.kind]

    def __iter__(self):
        for (key,) in self.index.db.execute('SELECT key FROM c3_sources WHERE kind=?', (self.kind,)):
            yield tuple(json.loads(key))

    def __getitem__(self, key):
        row = self.index.db.execute('SELECT source_hash FROM c3_sources WHERE kind=? AND key=?',
                                    (self.kind, canonical_json(key))).fetchone()
        if row is None: raise KeyError(key)
        return row[0]


def validate_c3_manifest(contract, manifest_path, *, project_root=None, db_path=None):
    """Verify C3 data only; returns no project/scope authorization or writer proof."""
    root = Path(project_root if project_root is not None else ROOT).resolve()
    path = Path(manifest_path).resolve()
    index = None
    try:
        raw = path.read_bytes()
        manifest = json.loads(raw)
        if not isinstance(manifest, dict) or 'chosen_partition' in manifest:
            raise ProductionScopeError('production requires C3 manifest, never a sample manifest')
        for key, expected in C3_IDENTITY.items():
            if manifest.get(key) != expected:
                raise ProductionScopeError(f'C3 {key} mismatch')
        files = [(path, hashlib.sha256(raw).hexdigest())]
        schema_paths = (ROOT / 'kag/schema/VietRoadTraffic.schema', ROOT / 'kag/schema/schema_contract.json')
        for schema_path, key in zip(schema_paths, ('schema_sha256', 'contract_sha256')):
            files.append((schema_path, C3_IDENTITY[key]))
        if json.loads(schema_paths[1].read_bytes()) != contract:
            raise ProductionScopeError('supplied schema contract differs from the approved contract')
        inputs = manifest['input_manifest']
        hashes = {}
        for row in inputs:
            name = row['name']
            if (not isinstance(name, str) or name in hashes or '\\' in name
                    or PurePosixPath(name).is_absolute() or PureWindowsPath(name).drive
                    or any(part in ('..', '.') for part in name.split('/')) or not name):
                raise ProductionScopeError('C3 input manifest has duplicate or escaping paths')
            hashes[name] = row['sha256']
            input_path = ((root / 'artifacts/inputs/xref-a3g2' / name)
                          if name in dict(ARTIFACT_HASHES) and name.startswith('xref_') else root / name)
            resolved = input_path.resolve()
            if not resolved.is_relative_to(root):
                raise ProductionScopeError('production input escapes project root')
            files.append((resolved, row['sha256']))
        if any(hashes.get(name) != expected for name, expected in ARTIFACT_HASHES):
            raise ProductionScopeError('required runtime input checksum is absent or differs')
        if db_path is not None:
            target = Path(db_path).resolve()
            protected = [source for source, _ in files] + [path.parent / name
                for name in ('nodes.jsonl', 'edges.jsonl', 'plan.sha256')]
            if target in [source.resolve() for source in protected]:
                raise ProductionScopeError('C3 index overlaps protected inputs')
        index = _C3Index(db_path)
        with index.db:
            index.db.execute('DELETE FROM c3_sources')
            for name, key in (('nodes', 'nodes_jsonl_sha256'), ('edges', 'edges_jsonl_sha256')):
                record_path = path.parent / (name + '.jsonl')
                files.append((record_path, C3_IDENTITY[key]))
                if _checksum(record_path) != C3_IDENTITY[key]:
                    raise ProductionScopeError(f'actual C3 {key} checksum mismatch')
                counts, total = Counter(), 0
                with record_path.open('rb') as stream:
                    for line in stream:
                        if line == b'\n': continue
                        spec = json.loads(line)
                        identity = (spec['type'], spec['id']) if name == 'nodes' else tuple(spec['tuple'])
                        if (any(not isinstance(part, str) or not part for part in identity)
                                or len(identity) != (2 if name == 'nodes' else 5)):
                            raise ProductionScopeError('invalid C3 source identity')
                        if name == 'nodes':
                            counts[spec['type'].rsplit('.', 1)[-1]] += 1
                            endpoints = (None, None)
                        else:
                            counts[identity[2]] += 1
                            endpoints = (canonical_json(identity[:2]), canonical_json(identity[3:]))
                        index.db.execute('INSERT INTO c3_sources VALUES (?,?,?,?,?,?,?)',
                            (name, total, canonical_json(identity), _spec_hash(spec), canonical_json(spec), *endpoints))
                        total += 1
                        del spec
                expected_counts = manifest['node_counts' if name == 'nodes' else 'edge_unique_counts']
                if (any(type(count) is not int or count < 0 for count in expected_counts.values())
                        or total != sum(expected_counts.values())
                        or any(counts[kind] != count for kind, count in expected_counts.items())):
                    raise ProductionScopeError('C3 manifest counts/uniqueness mismatch')
                index.counts[name] = total
            orphan = index.db.execute('''SELECT 1 FROM c3_sources e
                LEFT JOIN c3_sources f ON f.kind='nodes' AND f.key=e.from_key
                LEFT JOIN c3_sources t ON t.kind='nodes' AND t.key=e.to_key
                WHERE e.kind='edges' AND (f.key IS NULL OR t.key IS NULL) LIMIT 1''').fetchone()
            if orphan: raise ProductionScopeError('C3 edge endpoint missing')
        records = {name: _DiskRecords(index, name) for name in ('nodes', 'edges')}
        plan_path = path.parent / 'plan.sha256'
        expected_plan_bytes = (C3_IDENTITY['plan_sha256'] + '\n').encode('ascii')
        files.append((plan_path, hashlib.sha256(expected_plan_bytes).hexdigest()))
        plan = SimpleNamespace(**records, input_manifest=inputs,
            schema_sha256=manifest['schema_sha256'], contract_sha256=manifest['contract_sha256'])
        if plan_hash(plan) != C3_IDENTITY['plan_sha256']:
            raise ProductionScopeError('recomputed semantic C3 plan hash mismatch')
        node_hashes, edge_hashes = _DiskHashes(index, 'nodes'), _DiskHashes(index, 'edges')
        for file_path, expected in files:
            if _checksum(file_path) != expected:
                raise ProductionScopeError(f'{file_path.name}: C3 checksum mismatch')
        index.seal()
        files.append((index.path.resolve(), _checksum(index.path)))
        return dict(records, manifest=manifest, file_checksums=tuple(files), index=index,
                    node_hashes=node_hashes, edge_hashes=edge_hashes,
                    contract_hash=_spec_hash(contract))
    except ProductionScopeError:
        if index is not None: index.close()
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, sqlite3.DatabaseError):
        if index is not None: index.close()
        raise ProductionScopeError('invalid or unreadable production C3 manifest/input') from None


def validate_production_scope(settings, contract, manifest_path, *, project_root=None):
    """Grant production proof only after explicit settings and verified C3 data."""
    if not isinstance(settings, ProductionSettings):
        raise ProductionScopeError('explicit production settings are required')
    settings.validate()
    data = validate_c3_manifest(contract, manifest_path, project_root=project_root)
    scope = ProductionScope(settings, data['file_checksums'], data['node_hashes'],
                            data['edge_hashes'], data['contract_hash'], _PRODUCTION_PROOF)
    scope.verify_files(contract)
    return scope
