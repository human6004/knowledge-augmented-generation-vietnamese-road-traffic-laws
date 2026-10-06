"""Shared builder orchestration; explicit scope/inputs before any model or writer."""
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit

from kag.builder import production_scope as c3
from kag.builder.codec import canonical_json
from kag.run_state import ROOT, STAGES, RunBlocked


COMMON_LOCK_ROOT = Path('/run/kag-locks')
COMMON_LOCK_SOURCE = '/study/caoDATA-workspace/runs/.graph-locks'
FIELDS = {'scope', 'runtime_location', 'endpoints', 'database', 'project_id', 'project_name', 'namespace',
    'vector_dimensions', 'confirmation', 'paths', 'input_sha256', 'batch_size', 'heartbeat_seconds',
    'write_mode', 'vector_policy', 'model_identity', 'embedding_model', 'fallback_config', 'credential_env'}
PATH_FIELDS = {'c3_manifest', 'sample_manifest', 'vector_artifact', 'provenance', 'chunk_manifest',
               'source_checkpoint', 'run_root', 'lock_root'}


def _model_endpoint(value):
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or value.strip() != value):
            raise ValueError
    except (TypeError, ValueError, AttributeError):
        raise RunBlocked('CONFIG') from None


def _config(value):
    try:
        if not isinstance(value, dict) or set(value) - FIELDS:
            raise RunBlocked('CONFIG')
        config = json.loads(canonical_json(value))
        config.setdefault('scope', 'DENY')
        config.setdefault('write_mode', 'DENY')
        if config['scope'] not in ('C4_3A_MANIFEST_SAMPLE', 'PRODUCTION'):
            raise RunBlocked('SCOPE')
        if (config['runtime_location'] not in ('host', 'container')
                or config['write_mode'] not in ('NO_OP', 'WRITE')
                or config['vector_policy'] not in ('replay-existing', 'provider')
                or type(config['project_id']) is not int or config['project_id'] < 1
                or not isinstance(config['project_name'], str) or not config['project_name'].strip()
                or config['namespace'] != 'VietRoadTraffic'
                or type(config['vector_dimensions']) is not int or config['vector_dimensions'] != 3072
                or type(config['batch_size']) is not int or config['batch_size'] < 1
                or type(config['heartbeat_seconds']) not in (int, float)
                or not math.isfinite(config['heartbeat_seconds']) or config['heartbeat_seconds'] <= 0
                or not re.fullmatch(r'[a-z][a-z0-9.-]{0,62}', config['database'])):
            raise RunBlocked('CONFIG')
        if (config['scope'] == 'C4_3A_MANIFEST_SAMPLE' and
                (config['project_id'] != 2 or config['project_name'] != 'VietRoadTrafficC43A10Pct'
                 or config['write_mode'] != 'NO_OP' or config['vector_policy'] != 'replay-existing')):
            raise RunBlocked('SCOPE')
        if set(config['endpoints']) != {'openspg', 'neo4j_http', 'neo4j_uri'}:
            raise RunBlocked('CONFIG')
        location = config['runtime_location']
        # C4's localhost restriction remains intact, including shared container network namespaces.
        c3._endpoint(config['endpoints']['openspg'], ('http', 'https'),
                     'host' if config['scope'] == 'C4_3A_MANIFEST_SAMPLE' else location)
        c3._endpoint(config['endpoints']['neo4j_http'], ('http', 'https'), location)
        c3._endpoint(config['endpoints']['neo4j_uri'], ('bolt', 'neo4j', 'bolt+s', 'neo4j+s'), location)
        if set(config['paths']) != PATH_FIELDS or not isinstance(config['input_sha256'], dict):
            raise RunBlocked('CONFIG')
        for name, path in config['paths'].items():
            if name in ('run_root', 'lock_root', 'c3_manifest') or config['vector_policy'] == 'replay-existing':
                if name == 'sample_manifest' and config['scope'] == 'PRODUCTION' and path is None:
                    continue
                if not isinstance(path, str) or not Path(path).is_absolute():
                    raise RunBlocked('CONFIG')
            elif path is not None and (not isinstance(path, str) or not Path(path).is_absolute()):
                raise RunBlocked('CONFIG')
        expected_fields = {name for name, path in config['paths'].items()
                           if path is not None and name not in ('run_root', 'lock_root')}
        if set(config['input_sha256']) != expected_fields or any(
                not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest)
                for digest in config['input_sha256'].values()):
            raise RunBlocked('CONFIG')
        if set(config['credential_env']) != {'neo4j_username', 'neo4j_password', 'embedding_key'} or any(
                not isinstance(name, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]*', name)
                for name in config['credential_env'].values()):
            raise RunBlocked('CONFIG')
        endpoint, separator, model = config['model_identity'].rpartition('|')
        if not separator or not model.strip():
            raise RunBlocked('CONFIG')
        _model_endpoint(endpoint)
        if config['vector_policy'] == 'provider':
            embedding = config['embedding_model']
            if (set(embedding) != {'type', 'base_url', 'model', 'timeout'} or embedding['type'] != 'openai'
                    or config['model_identity'] != embedding['base_url'].rstrip('/') + '|' + embedding['model']
                    or type(embedding['timeout']) not in (int, float) or not math.isfinite(embedding['timeout'])
                    or embedding['timeout'] <= 0):
                raise RunBlocked('CONFIG')
            _model_endpoint(embedding['base_url'])
        elif config['embedding_model'] is not None:
            raise RunBlocked('CONFIG')
        if not isinstance(config['fallback_config'], dict):
            raise RunBlocked('CONFIG')
        return config
    except (c3.ProductionScopeError, KeyError, TypeError, ValueError, AttributeError) as error:
        if isinstance(error, RunBlocked): raise
        raise RunBlocked('CONFIG') from None


def load_config(path):
    try:
        return _config(json.loads(Path(path).read_bytes()))
    except (OSError, ValueError, TypeError) as error:
        if isinstance(error, RunBlocked): raise
        raise RunBlocked('CONFIG') from None


def _shared_lock_root(path):
    root = Path(path).resolve()
    if root != COMMON_LOCK_ROOT or not root.is_dir():
        raise RunBlocked('LOCK')
    try:
        for line in Path('/proc/self/mountinfo').read_text().splitlines():
            fields = line.split()
            boundary = fields.index('-')
            if (fields[4] == str(COMMON_LOCK_ROOT) and fields[3] == COMMON_LOCK_SOURCE
                    and fields[boundary + 1] == '9p'
                    and fields[boundary + 2].replace('\\134', '\\').rstrip('\\').upper() == 'D:'):
                return {'mountpoint': str(root), 'host_path': 'D:/study/caoDATA-workspace/runs/.graph-locks'}
    except (OSError, ValueError, IndexError):
        pass
    raise RunBlocked('LOCK')


def _paths(config):
    protected = [Path(path).resolve() for name, path in config['paths'].items()
                 if path is not None and name not in ('run_root', 'lock_root')]
    for name in ('run_root', 'lock_root'):
        root = Path(config['paths'][name]).resolve()
        if root.is_relative_to(ROOT) or ROOT.is_relative_to(root) or (root.exists() and not root.is_dir()):
            raise RunBlocked('CONFIG')
        for source in protected:
            if root.is_relative_to(source) or source.is_relative_to(root):
                raise RunBlocked('CONFIG')
    return _shared_lock_root(config['paths']['lock_root'])


def _files(config):
    checksums = []
    for name, expected in config['input_sha256'].items():
        path = Path(config['paths'][name]).resolve()
        if c3._checksum(path) != expected:
            raise RunBlocked('INTEGRITY')
        checksums.append((path, expected))
    return checksums


def _sample_sources(data, manifest):
    if (manifest['chosen_partition'] != 5 or manifest['partition_algorithm'] !=
            "int(sha256(doc_id.encode('utf-8')).hexdigest(),16) % 10"):
        raise RunBlocked('PLAN')
    docs = {n['id'] for n in data['nodes'] if n['type'] == 'VietRoadTraffic.LegalDocument'
            and int(hashlib.sha256(n['id'].encode()).hexdigest(), 16) % 10 == 5}
    if sorted(docs) != manifest['selected_document_ids'] or len(docs) != len(manifest['selected_document_ids']):
        raise RunBlocked('PLAN')
    nodes = [n for n in data['nodes'] if (n['id'] if n['type'] == 'VietRoadTraffic.LegalDocument'
                                        else n['properties']['docId']) in docs]
    keys = {(n['type'], n['id']) for n in nodes}
    edges = [e for e in data['edges'] if (e['tuple'][0], e['tuple'][1]) in keys
             and (e['tuple'][3], e['tuple'][4]) in keys]
    expected = {'nodes': c3.C3_IDENTITY['nodes_jsonl_sha256'], 'edges': c3.C3_IDENTITY['edges_jsonl_sha256'],
                'plan': c3.C3_IDENTITY['plan_sha256']}
    if manifest['c3_sha256'] != expected:
        raise RunBlocked('PLAN')
    return nodes, edges


def preflight(config, *, project_client, reader):
    config = _config(config)
    mount = _paths(config)
    try:
        checksums = _files(config)
        from kag.bootstrap import initialize
        initialize()
        from kag.builder.writer_adapter import discover_manifest_project, discover_production_project
        contract = json.loads((ROOT / 'kag/schema/schema_contract.json').read_bytes())
        if config['scope'] == 'PRODUCTION':
            settings = c3.ProductionSettings(scope=config['scope'], runtime_location=config['runtime_location'],
                host_addr=config['endpoints']['openspg'], neo4j_uri=config['endpoints']['neo4j_uri'],
                project_name=config['project_name'], namespace=config['namespace'], expected_project_id=config['project_id'],
                vector_dimensions=config['vector_dimensions'], confirmation=config['confirmation'])
            writer_config = discover_production_project(project_client, settings, contract, config['paths']['c3_manifest'])
            proof = writer_config.production_scope
            node_hashes, edge_hashes = dict(proof.node_hashes), dict(proof.edge_hashes)
            checksums.extend(proof.file_checksums)
        else:
            data = c3.validate_c3_manifest(contract, config['paths']['c3_manifest'])
            manifest = json.loads(Path(config['paths']['sample_manifest']).read_bytes())
            nodes, edges = _sample_sources(data, manifest)
            writer_config = discover_manifest_project(project_client, config['endpoints']['openspg'], contract,
                config['paths']['sample_manifest'], nodes, edges)
            node_hashes = {(n['type'], n['id']): data['node_hashes'][(n['type'], n['id'])] for n in nodes}
            edge_hashes = {tuple(e['tuple']): data['edge_hashes'][tuple(e['tuple'])] for e in edges}
            checksums.extend(data['file_checksums'])
        database_id = reader.database_identity()
        if not isinstance(database_id, str) or not database_id.strip():
            raise RunBlocked('LOCK')
        identity = {'scope': config['scope'], 'project_id': writer_config.project_id,
            'project_name': writer_config.project_name, 'namespace': writer_config.namespace,
            'endpoints': config['endpoints'], 'database': config['database'], 'database_id': database_id,
            'batch_size': config['batch_size'], 'model_identity': config['model_identity'], 'dimension': 3072,
            'write_mode': config['write_mode'], 'vector_policy': config['vector_policy'],
            'config_hash': c3._spec_hash(config), 'input_hashes': dict(config['input_sha256']),
            'c3': dict(c3.C3_IDENTITY), 'python': '3.10.16',
            'vendor_commit': 'fdab15b3929d2ee40dfcdd388f90233096a6afc9', 'common_lock': mount}
        return {'writer_config': writer_config, 'contract': contract, 'identity': identity, 'database_id': database_id,
                'node_hashes': node_hashes, 'edge_hashes': edge_hashes, 'file_checksums': tuple(checksums)}
    except (c3.ProductionScopeError, OSError, KeyError, ValueError, TypeError) as error:
        if isinstance(error, RunBlocked): raise
        raise RunBlocked('SCOPE') from None


def _revalidate(verified):
    for path, expected in verified['file_checksums']:
        if c3._checksum(path) != expected:
            raise RunBlocked('INTEGRITY')
    verified['writer_config'].__post_init__()


def _jsonl(path):
    with Path(path).open('r', encoding='utf-8') as stream:
        for line in stream:
            if not line.endswith('\n') or not line.strip():
                raise RunBlocked('INTEGRITY')
            yield json.loads(line)


def plan_sources(config, *, db_path, verified):
    _revalidate(verified)
    path = Path(db_path).resolve()
    if path.is_relative_to(ROOT) or any(path == Path(source).resolve()
            for name, source in config['paths'].items() if source and name not in ('run_root', 'lock_root')):
        raise RunBlocked('CONFIG')
    db = sqlite3.connect(path)
    try:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS runner_sources (kind TEXT,ordinal INTEGER,key TEXT,source_hash TEXT,payload TEXT,
                PRIMARY KEY(kind,ordinal),UNIQUE(kind,key));
            CREATE TABLE IF NOT EXISTS runner_plan (key TEXT PRIMARY KEY,value TEXT);
        ''')
        prior = db.execute('SELECT value FROM runner_plan WHERE key=\'receipt\'').fetchone()
        if prior:
            receipt = json.loads(prior[0])
            if receipt['identity_hash'] != c3._spec_hash(verified['identity']):
                raise RunBlocked('INTEGRITY')
            for kind, hashes in (('nodes', verified['node_hashes']), ('edges', verified['edge_hashes'])):
                rows = db.execute('SELECT ordinal,key,source_hash,payload FROM runner_sources WHERE kind=? ORDER BY ordinal', (kind,))
                count, ordered = 0, hashlib.sha256()
                for ordinal, key, digest, payload in rows:
                    if ordinal != count or hashes.get(tuple(json.loads(key))) != digest or c3._spec_hash(json.loads(payload)) != digest:
                        raise RunBlocked('INTEGRITY')
                    ordered.update((payload + '\n').encode())
                    count += 1
                if count != len(hashes) or count != receipt[kind] or ordered.hexdigest() != receipt[kind + '_hash']:
                    raise RunBlocked('INTEGRITY')
            return receipt
        result = {'identity_hash': c3._spec_hash(verified['identity'])}
        from kag.builder.writer_adapter import to_subgraphs
        with db:
            db.execute('DELETE FROM runner_sources')
            directory = Path(config['paths']['c3_manifest']).parent
            for kind, hashes in (('nodes', verified['node_hashes']), ('edges', verified['edge_hashes'])):
                count, digest = 0, hashlib.sha256()
                for spec in _jsonl(directory / (kind + '.jsonl')):
                    key = (spec['type'], spec['id']) if kind == 'nodes' else tuple(spec['tuple'])
                    if key not in hashes:
                        if config['scope'] == 'PRODUCTION': raise RunBlocked('PLAN')
                        continue
                    source_hash = c3._spec_hash(spec)
                    if hashes[key] != source_hash or (kind == 'nodes' and any(k.startswith('_') for k in spec['properties'])):
                        raise RunBlocked('PLAN')
                    to_subgraphs([spec], 1, kind, verified['writer_config'])
                    payload = canonical_json(spec)
                    db.execute('INSERT INTO runner_sources VALUES (?,?,?,?,?)',
                               (kind, count, canonical_json(key), source_hash, payload))
                    digest.update((payload + '\n').encode())
                    count += 1
                if count != len(hashes): raise RunBlocked('PLAN')
                result[kind], result[kind + '_hash'] = count, digest.hexdigest()
            db.execute('INSERT OR REPLACE INTO runner_plan VALUES (\'receipt\',?)', (canonical_json(result),))
        return result
    except (sqlite3.DatabaseError, KeyError, TypeError, ValueError) as error:
        if isinstance(error, RunBlocked): raise
        raise RunBlocked('PLAN') from None
    finally:
        db.close()


def iter_source_batches(db_path, kind, batch_size):
    if kind not in ('nodes', 'edges') or type(batch_size) is not int or batch_size < 1:
        raise RunBlocked('CONFIG')
    db = sqlite3.connect(Path(db_path).resolve().as_uri() + '?mode=ro', uri=True)
    try:
        rows = db.execute('SELECT payload FROM runner_sources WHERE kind=? ORDER BY ordinal', (kind,))
        while True:
            batch = rows.fetchmany(batch_size)
            if not batch: return
            yield [json.loads(row[0]) for row in batch]
    finally:
        db.close()
