"""Shared builder orchestration; explicit scope/inputs before any model or writer."""
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import os
import uuid
from collections import Counter, defaultdict
from urllib.parse import urlsplit

from kag.builder import production_scope as c3
from kag.builder.codec import canonical_json
from kag.run_state import ROOT, STAGES, RunBlocked, RunState, GraphLock, atomic_json, validate_run_directory


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
        from kag.builder.resilient_vectorizer import ResilientVectorizer
        validator = ResilientVectorizer(None, model_identity=config['model_identity'], dimension=3072,
                                       embedding_fallback=config['fallback_config'])
        validator.close()
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
    except (TimeoutError, ConnectionError):
        raise RuntimeError('Graph transport unavailable.') from None
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
        cursor = -1
        while True:
            # Finish the read transaction before yielding: RunState writes this same ledger.
            batch = db.execute('SELECT ordinal,payload FROM runner_sources WHERE kind=? AND ordinal>? '
                               'ORDER BY ordinal LIMIT ?', (kind, cursor, batch_size)).fetchall()
            if not batch: return
            cursor = batch[-1][0]
            yield [json.loads(row[1]) for row in batch]
    finally:
        db.close()


def _clients(config, project_client, reader):
    from kag.bootstrap import initialize
    initialize()
    if project_client is None:
        from knext.project.client import ProjectClient
        project_client = ProjectClient(host_addr=config['endpoints']['openspg'])
    if reader is None:
        from kag.verify import Neo4jReadClient
        names = config['credential_env']
        username, password = os.environ.get(names['neo4j_username']), os.environ.get(names['neo4j_password'])
        if not username or not password: raise RunBlocked('CONFIG')
        reader = Neo4jReadClient(config['endpoints']['neo4j_http'], config['database'],
                                 username=username, password=password, timeout=60)
    return project_client, reader


def _provider(config, verified):
    from kag.common.vectorize_model.openai_model import OpenAIVectorizeModel
    from kag.builder.component.vectorizer.batch_vectorizer import BatchVectorizer
    from kag.builder.resilient_vectorizer import TARGETS
    key = os.environ.get(config['credential_env']['embedding_key'])
    if not key: raise RunBlocked('CONFIG')
    model = dict(config['embedding_model']); model.pop('type')
    adapter = OpenAIVectorizeModel(**model, api_key=key, vector_dimensions=3072)
    # Upstream constructor reads global KAG config. Supply its exact attributes explicitly,
    # as the existing scoped writer does; retain upstream generator/adapter behavior.
    batch = BatchVectorizer.__new__(BatchVectorizer)
    batch.kag_project_config = verified['writer_config']
    batch.project_id = verified['writer_config'].project_id
    batch.vectorize_model, batch.sparse_vectorize_model = adapter, None
    batch.batch_size = config['batch_size']
    batch.disable_generation = [local + '.name' for local in (*TARGETS, 'Entity')]
    batch.vec_meta = (defaultdict(list, {local: [field for _, field in targets]
                                       for local, targets in TARGETS.items()}), {})
    return batch


def _publish_jsonl(path, records):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    count, digest = 0, hashlib.sha256()
    try:
        with temporary.open('xb') as stream:
            for record in records:
                line = (canonical_json(record) + '\n').encode()
                stream.write(line); digest.update(line); count += 1
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return {'file': path.name, 'sha256': digest.hexdigest(), 'count': count}


def _check_output(state, result):
    path = state._owned_file(result['file'])
    if not path.is_file() or c3._checksum(path) != result['sha256']:
        raise RunBlocked('INTEGRITY')
    return path


def _replay_index(config, state, verified):
    from kag.verify import index_expected
    path = state._owned_file('replay.sqlite3')
    db = sqlite3.connect(path)
    try:
        db.execute('CREATE TABLE IF NOT EXISTS replay_nodes (key TEXT PRIMARY KEY,payload TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS replay_jobs (key TEXT PRIMARY KEY,payload TEXT)')
        provenance = json.loads(Path(config['paths']['provenance']).read_bytes())
        chunks = json.loads(Path(config['paths']['chunk_manifest']).read_bytes())
        if provenance['model_identity'] != config['model_identity'] or provenance['dimension'] != 3072:
            raise RunBlocked('PROVENANCE')
        aggregates = [job['fallback'] for job in provenance['jobs'] if job.get('embedding_method') == 'CHUNK_AGGREGATED']
        if (chunks['source_count'] != len(aggregates) or
                sorted(canonical_json(s) for s in chunks['sources']) != sorted(canonical_json(s) for s in aggregates)):
            raise RunBlocked('PROVENANCE')
        with db:
            db.execute('DELETE FROM replay_nodes'); db.execute('DELETE FROM replay_jobs')
            for spec in _jsonl(config['paths']['vector_artifact']):
                key = (spec['type'], spec['id'])
                original = dict(spec, properties={k: v for k, v in spec['properties'].items() if not k.startswith('_')})
                if verified['node_hashes'].get(key) != c3._spec_hash(original): raise RunBlocked('PLAN')
                db.execute('INSERT INTO replay_nodes VALUES (?,?)', (canonical_json(key), canonical_json(spec)))
            if db.execute('SELECT COUNT(*) FROM replay_nodes').fetchone()[0] != len(verified['node_hashes']):
                raise RunBlocked('VECTORS')
            for job in provenance['jobs']:
                if job.get('embedding_method') == 'CHUNK_AGGREGATED' and job['fallback_config'] != config['fallback_config']:
                    raise RunBlocked('PROVENANCE')
                key = [job['node_type'], job['node_id'], job['property']]
                db.execute('INSERT INTO replay_jobs VALUES (?,?)', (canonical_json(key), canonical_json(job)))
        def nodes():
            for (payload,) in db.execute('SELECT payload FROM replay_nodes ORDER BY key'): yield json.loads(payload)
        index_expected(state._owned_file('expected.sqlite3'), nodes(), (e for b in iter_source_batches(state.run_dir / 'ledger.sqlite3',
            'edges', config['batch_size']) for e in b), contract=verified['contract'], provenance=iter(provenance['jobs']))
    except (KeyError, sqlite3.DatabaseError, ValueError, TypeError) as error:
        if isinstance(error, RunBlocked): raise
        raise RunBlocked('PROVENANCE') from None
    finally:
        db.close()
    return path


def _cached_batch(config, path, originals):
    from kag.builder.resilient_vectorizer import TARGETS
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    old = sqlite3.connect(Path(config['paths']['source_checkpoint']).resolve().as_uri() + '?mode=ro', uri=True)
    nodes, jobs = [], []
    try:
        for original in originals:
            row = db.execute('SELECT payload FROM replay_nodes WHERE key=?',
                             (canonical_json([original['type'], original['id']]),)).fetchone()
            if row is None: raise RunBlocked('VECTORS')
            node = json.loads(row[0]); nodes.append(node)
            for prop, field in TARGETS[original['type'].rsplit('.', 1)[-1]]:
                key = canonical_json([original['type'], original['id'], prop])
                row = db.execute('SELECT payload FROM replay_jobs WHERE key=?', (key,)).fetchone()
                cached = old.execute('SELECT state FROM jobs WHERE identity=?', (key,)).fetchone()
                if row is None or cached is None: raise RunBlocked('VECTORS')
                job, entry = json.loads(row[0]), json.loads(cached[0])
                fields = ('node_type', 'node_id', 'property', 'source_sha256', 'model_identity', 'dimension',
                          'status', 'embedding_method')
                if (any(entry.get(k) != job[k] for k in fields)
                        or entry.get('vector') != node['properties'].get(field)
                        or any(entry.get(k) != job.get(k) for k in ('fallback', 'fallback_config', 'direct_failure'))):
                    raise RunBlocked('PROVENANCE')
                jobs.append(job)
    except (sqlite3.DatabaseError, KeyError, TypeError, ValueError) as error:
        if isinstance(error, RunBlocked): raise
        raise RunBlocked('VECTORS') from None
    finally:
        db.close(); old.close()
    return nodes, jobs


class _Interrupted(Exception):
    pass


def _batch_rows(state, stage):
    return [(key, json.loads(result)) for key, result in state.db.execute(
        "SELECT key,result FROM run_batches WHERE stage=? AND state='CONFIRMED' ORDER BY CAST(key AS INTEGER)", (stage,))]


def _confirmed_progress(state, stage):
    return sum(result['count'] for _, result in _batch_rows(state, stage))


def _stop(stop, stage, ordinal):
    if stop == (stage, ordinal + 1): raise _Interrupted()


def _vectorize(config, state, verified, replay_path, factory, stop):
    from kag.builder.resilient_vectorizer import ResilientVectorizer, IncompleteVectorization
    total = len(verified['node_hashes'])
    if not state.completed_stage('vectorize'):
        state.update('vectorize', 'RUNNING', _confirmed_progress(state, 'vectorize'), total)
    engine = None
    try:
        for ordinal, originals in enumerate(iter_source_batches(state.run_dir / 'ledger.sqlite3', 'nodes', config['batch_size'])):
            digest = c3._spec_hash(originals)
            prior = state.begin_batch('vectorize', str(ordinal), digest)
            if prior['state'] == 'CONFIRMED':
                _check_output(state, prior['result']['nodes']); _check_output(state, prior['result']['jobs'])
                continue
            if engine is None:
                batch = None if replay_path else (factory or _provider)(config, verified)
                engine = ResilientVectorizer(batch, model_identity=config['model_identity'], dimension=3072,
                    checkpoint_path=state._owned_file('vectors.sqlite3'), embedding_fallback=config['fallback_config'])
            jobs = None
            if replay_path:
                cached, jobs = _cached_batch(config, replay_path, originals)
                engine.import_successes(originals, cached, artifact_model_identity=config['model_identity'],
                                        artifact_dimension=3072, artifact_jobs=jobs)
            try:
                result = engine.run(originals); result.require_complete()
            except IncompleteVectorization:
                raise RunBlocked('VECTORS') from None
            output = _publish_jsonl(state._owned_file(f'vectors-{ordinal}.jsonl'), result.iter_nodes())
            sidecar = _publish_jsonl(state._owned_file(f'jobs-{ordinal}.jsonl'), iter(jobs if jobs is not None else result.jobs))
            records = jobs if jobs is not None else result.jobs
            methods = Counter(j['embedding_method'] for j in records if j['status'] == 'SUCCESS')
            state.confirm_batch('vectorize', str(ordinal), dict(count=len(originals), nodes=output, jobs=sidecar,
                embedding_calls=result.provider_requests, candidates=len(records),
                nonempty=result.counts['successful'], skipped_empty=result.counts['skipped_empty'], provenance=dict(methods)))
            state.update('vectorize', 'RUNNING', _confirmed_progress(state, 'vectorize'), total)
            _stop(stop, 'vectorize', ordinal)
        methods, counts = Counter(), Counter()
        for _, result in _batch_rows(state, 'vectorize'):
            methods.update(result['provenance'])
            counts.update({k: result[k] for k in ('count', 'embedding_calls', 'candidates', 'nonempty', 'skipped_empty')})
        receipt = dict(counts, provenance=dict(methods), dimension=3072)
        if not state.completed_stage('vectorize'): state.finish_stage('vectorize', receipt)
        elif state.completed_stage('vectorize') != receipt: raise RunBlocked('INTEGRITY')
    finally:
        if engine is not None: engine.close()


def _export(config, state, stop):
    stage = 'export-artifact'
    previous = state.completed_stage(stage)
    if previous:
        for result in previous.values(): _check_output(state, result)
        return previous
    rows = _batch_rows(state, 'vectorize')
    state.update(stage, 'RUNNING', _confirmed_progress(state, stage), len(rows))
    for ordinal, (_, result) in enumerate(rows):
        prior = state.begin_batch(stage, str(ordinal), c3._spec_hash(result))
        _check_output(state, result['nodes']); _check_output(state, result['jobs'])
        if prior['state'] != 'CONFIRMED':
            state.confirm_batch(stage, str(ordinal), {'count': 1})
            state.update(stage, 'RUNNING', _confirmed_progress(state, stage), len(rows))
            _stop(stop, stage, ordinal)
    def records(kind):
        for _, result in rows: yield from _jsonl(_check_output(state, result[kind]))
    output = {'nodes': _publish_jsonl(state._owned_file('vectorized_nodes.jsonl'), records('nodes')),
              'jobs': _publish_jsonl(state._owned_file('provenance.jsonl'), records('jobs'))}
    if output['nodes']['count'] != state.completed_stage('vectorize')['count']: raise RunBlocked('INTEGRITY')
    state.finish_stage(stage, output)
    return output


def _node_batches(state, output, batch_size):
    batch = []
    for node in _jsonl(_check_output(state, output['nodes'])):
        batch.append(node)
        if len(batch) == batch_size:
            yield batch; batch = []
    if batch: yield batch


def _graph_batches(config, state, verified, reader, writer, kind, output, stop):
    from kag.builder.writer_adapter import to_subgraphs
    from kag.verify import verify_batch
    stage = 'write-' + kind
    total = len(verified['node_hashes' if kind == 'nodes' else 'edge_hashes'])
    if not state.completed_stage(stage): state.update(stage, 'RUNNING', _confirmed_progress(state, stage), total)
    batches = (_node_batches(state, output, config['batch_size']) if kind == 'nodes' else
               iter_source_batches(state.run_dir / 'ledger.sqlite3', kind, config['batch_size']))
    for ordinal, specs in enumerate(batches):
        key, digest = str(ordinal), c3._spec_hash(specs)
        existed = state.db.execute('SELECT state FROM run_batches WHERE stage=? AND key=?', (stage, key)).fetchone()
        prior = state.begin_batch(stage, key, digest)
        if prior['state'] == 'CONFIRMED': continue
        writes = 0
        if config['write_mode'] == 'WRITE' and existed is None:
            verified['writer_config'].__post_init__()
            for graph in to_subgraphs(specs, config['batch_size'], kind, verified['writer_config']):
                writer.write_subgraph(graph, kind); writes += 1
        # Any prior INTENT is uncertain: readback only; never blind resend.
        result = verify_batch(reader, specs, kind=kind, contract=verified['contract'])
        state.confirm_batch(stage, key, dict(result, count=len(specs), graph_writes=writes))
        state.update(stage, 'RUNNING', _confirmed_progress(state, stage), total)
        _stop(stop, stage, ordinal)
    result = {'count': total, 'graph_writes': sum(r['graph_writes'] for _, r in _batch_rows(state, stage))}
    if not state.completed_stage(stage): state.finish_stage(stage, result)
    elif state.completed_stage(stage) != result: raise RunBlocked('INTEGRITY')


def _execute(config, run_id, resume, project_client, reader, vectorizer_factory, writer_factory, stop, verify_only=False):
    state, lock, directory, identity = None, None, None, None
    try:
        config = _config(config)
        directory = validate_run_directory(config['paths']['run_root'], run_id,
            read_only_paths=[v for k, v in config['paths'].items() if v and k not in ('run_root', 'lock_root')])
        project_client, reader = _clients(config, project_client, reader)
        verified = preflight(config, project_client=project_client, reader=reader)
        identity = dict(verified['identity'], run_id=run_id)
        lock = GraphLock(config['paths']['lock_root'], verified['database_id'], dict(identity,
            openspg_endpoint=config['endpoints']['openspg'], neo4j_endpoint=config['endpoints']['neo4j_http']))
        lock.acquire()
        state = RunState(directory, identity, resume=resume)
        state.start_heartbeat(config['heartbeat_seconds'])
        skipped = state.db.execute("SELECT COUNT(*) FROM run_batches WHERE state='CONFIRMED'").fetchone()[0]
        if not state.completed_stage('preflight'):
            state.update('preflight', 'RUNNING', 0, 1); state.update('preflight', 'RUNNING', 1, 1)
            state.finish_stage('preflight', {'identity_hash': c3._spec_hash(identity)})
        plan = plan_sources(config, db_path=state.run_dir / 'ledger.sqlite3', verified=verified)
        if not state.completed_stage('plan'):
            state.update('plan', 'RUNNING', plan['nodes'] + plan['edges'], plan['nodes'] + plan['edges'])
            state.finish_stage('plan', plan)
        from kag.verify import index_expected, verify_graph
        if verify_only:
            output = state.completed_stage('export-artifact')
            if output is None: raise RunBlocked('INTEGRITY')
            for result in output.values(): _check_output(state, result)
        else:
            replay = _replay_index(config, state, verified) if config['vector_policy'] == 'replay-existing' else None
            _vectorize(config, state, verified, replay, vectorizer_factory, stop)
            output = _export(config, state, stop)
        expected_path = state._owned_file('expected.sqlite3')
        expected = index_expected(expected_path, _jsonl(_check_output(state, output['nodes'])),
            (e for b in iter_source_batches(state.run_dir / 'ledger.sqlite3', 'edges', config['batch_size']) for e in b),
            contract=verified['contract'], provenance=_jsonl(_check_output(state, output['jobs'])))
        if verify_only:
            result = verify_graph(reader, db_path=expected_path, contract=verified['contract'],
                                  batch_size=config['batch_size'])
            atomic_json(state._owned_file('verification.json'), result)
            state.update('verify', 'PASS', 1, 1)
            return 0
        writer = None
        if config['write_mode'] == 'WRITE':
            from kag.builder.writer_adapter import NativeIntegerKGWriter
            writer = (writer_factory or NativeIntegerKGWriter)(verified['writer_config'])
        _graph_batches(config, state, verified, reader, writer, 'nodes', output, stop)
        # Recheck the full barrier on resume before any remaining edge dispatch.
        barrier = verify_graph(reader, db_path=expected_path, contract=verified['contract'],
                               batch_size=config['batch_size'], nodes_only=True)
        if not state.completed_stage('verify-nodes'):
            state.update('verify-nodes', 'RUNNING', barrier['nodes']['total'], plan['nodes'])
            state.finish_stage('verify-nodes', barrier)
        elif state.completed_stage('verify-nodes') != barrier: raise RunBlocked('INTEGRITY')
        if writer:
            for batch in iter_source_batches(state.run_dir / 'ledger.sqlite3', 'nodes', config['batch_size']):
                writer._mark_nodes_verified(batch)
        _graph_batches(config, state, verified, reader, writer, 'edges', output, stop)
        result = verify_graph(reader, db_path=expected_path, contract=verified['contract'],
                              batch_size=config['batch_size'])
        if not state.completed_stage('verify'):
            state.update('verify', 'RUNNING', 1, 1); state.finish_stage('verify', result)
        elif state.completed_stage('verify') != result: raise RunBlocked('INTEGRITY')
        _revalidate(verified)
        if not state.completed_stage('release'):
            vectors = state.completed_stage('vectorize')
            release = {'kind': 'SAMPLE/NO_OP' if config['scope'] == 'C4_3A_MANIFEST_SAMPLE' else config['scope'] + '/' + config['write_mode'],
                'embedding_calls': vectors['embedding_calls'], 'graph_writes': sum(
                    state.completed_stage('write-' + kind)['graph_writes'] for kind in ('nodes', 'edges')),
                'skipped_batches': skipped, 'expected': expected, 'fingerprint': result['fingerprint'],
                'artifacts': output, 'vectors': vectors}
            state.update('release', 'RUNNING', 1, 1); state.finish_stage('release', release)
        else:
            state.update('release', 'PASS', 1, 1)
            state._receipt()
        return 0
    except Exception as error:
        code = 'INTERRUPTED' if isinstance(error, _Interrupted) else error.code if isinstance(error, RunBlocked) else 'RUNTIME'
        blocked = isinstance(error, RunBlocked)
        # Preflight/lock refusals still receive a sanitized status when a safe fresh path exists.
        if state is None and directory is not None and not directory.exists():
            try:
                state = RunState(directory, identity or {'run_id': run_id, 'scope': config['scope']})
            except Exception:
                pass
        if state is not None:
            try:
                state.update(state.status['stage'], 'BLOCKED' if blocked else 'ERROR',
                             state.status['done'], state.status['total'], error_code=code)
                state._receipt()
            except Exception:
                pass
        return 2 if blocked else 1
    finally:
        if state is not None: state.close()
        if lock is not None and lock.acquired: lock.release()


def run(config, *, run_id, resume=False, project_client=None, reader=None, vectorizer_factory=None,
        writer_factory=None, stop_after_batch=None):
    return _execute(config, run_id, resume, project_client, reader, vectorizer_factory, writer_factory, stop_after_batch)


def verify_run(config, *, run_id, reader=None, project_client=None):
    return _execute(config, run_id, True, project_client, reader, None, None, None, verify_only=True)
