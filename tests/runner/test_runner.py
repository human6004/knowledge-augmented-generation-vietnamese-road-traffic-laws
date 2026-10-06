"""Runner preflight uses real pinned SDK discovery and builder scope proofs."""
import copy
import hashlib
import importlib
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from kag.builder.codec import canonical_json
from kag.builder.graph_plan import plan_hash
from kag.builder import production_scope as scope
from kag.run_state import GraphLock, RunBlocked
from test_verify import CONTRACT, MODEL, fixture


ROOT = Path(__file__).resolve().parents[2]


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Projects:
    def __init__(self, endpoint, records):
        self._host_addr = endpoint
        self.records = records
        self._rest_client = self
        self.reads = 0

    def get(self, **conditions):
        self.reads += 1
        return next((r for r in self.records if str(r['id']) == str(conditions['id'])), None)

    def project_get(self):
        self.reads += 1
        return self.records


class Database:
    def __init__(self, identity='physical-fixture-db'):
        self.identity = identity

    def database_identity(self):
        return self.identity


class RunnerPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kag.bootstrap import initialize
        initialize()
        cls.adapter = importlib.import_module('kag.builder.writer_adapter')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.nodes, self.edges, self.jobs = fixture()
        document = next('D' + str(i) for i in range(100)
                        if int(hashlib.sha256(('D' + str(i)).encode()).hexdigest(), 16) % 10 == 5)
        replacements = {'D1': document, 'D1::D1': document + '::D1'}
        for node in self.nodes:
            node['id'] = node['name'] = replacements.get(node['id'], node['id'])
            if 'docId' in node['properties']: node['properties']['docId'] = document
            if 'unitId' in node['properties']: node['properties']['unitId'] = document + '::D1'
        from kag.builder.mapping import application_edge_key
        self.edges[0]['tuple'][1], self.edges[0]['tuple'][4] = document, document + '::D1'
        self.edges[0]['application_edge_key'] = application_edge_key(self.edges[0]['tuple'])
        self.originals = [dict(n, properties={k: v for k, v in n['properties'].items() if not k.startswith('_')})
                          for n in self.nodes]
        for name, records in (('nodes', self.originals), ('edges', self.edges)):
            (self.root / (name + '.jsonl')).write_text(''.join(canonical_json(r) + '\n' for r in records),
                                                     encoding='utf-8', newline='\n')
        schema_dir = self.root / 'kag/schema'
        schema_dir.mkdir(parents=True)
        for filename in ('VietRoadTraffic.schema', 'schema_contract.json'):
            (schema_dir / filename).write_bytes((ROOT / 'kag/schema' / filename).read_bytes())
        (self.root / 'fixture.txt').write_bytes(b'fixture')
        inputs = [{'name': 'fixture.txt', 'sha256': checksum(self.root / 'fixture.txt')}]
        pins = dict(scope.C3_IDENTITY)
        pins.update(nodes_jsonl_sha256=checksum(self.root / 'nodes.jsonl'),
                    edges_jsonl_sha256=checksum(self.root / 'edges.jsonl'))
        pins['plan_sha256'] = plan_hash(SimpleNamespace(nodes=self.originals, edges=self.edges,
            input_manifest=inputs, schema_sha256=pins['schema_sha256'], contract_sha256=pins['contract_sha256']))
        manifest = dict(pins, input_manifest=inputs, node_counts={'LegalDocument': 1, 'LegalUnit': 1, 'TrafficSign': 1},
                        edge_unique_counts={'hasUnit': 1})
        (self.root / 'manifest.json').write_text(canonical_json(manifest), encoding='utf-8')
        (self.root / 'plan.sha256').write_text(pins['plan_sha256'] + '\n', encoding='ascii')
        policy = dict(self.adapter._C43A_POLICY, nodes=3, edges=1,
            nodes_sha256=hashlib.sha256(''.join('\t'.join(k) + '\n' for k in
                        sorted((n['type'], n['id']) for n in self.originals)).encode()).hexdigest(),
            edges_sha256=hashlib.sha256(''.join(canonical_json(tuple(e['tuple'])) + '\n'
                        for e in sorted(self.edges, key=lambda e: e['tuple'])).encode()).hexdigest())
        sample = dict(chosen_partition=5, partition_algorithm="int(sha256(doc_id.encode('utf-8')).hexdigest(),16) % 10",
            selected_document_ids=[document], counts_by_type=dict(manifest['node_counts'], total=3), total_edges=1,
            selected_node_identity_sha256=policy['nodes_sha256'], selected_edge_tuple_sha256=policy['edges_sha256'],
            c3_sha256={'nodes': pins['nodes_jsonl_sha256'], 'edges': pins['edges_jsonl_sha256'], 'plan': pins['plan_sha256']})
        (self.root / 'sample.json').write_text(canonical_json(sample), encoding='utf-8')
        (self.root / 'vectors.jsonl').write_text(''.join(canonical_json(n) + '\n' for n in self.nodes), encoding='utf-8')
        for job in self.jobs:
            job['node_id'] = replacements.get(job['node_id'], job['node_id'])
            if job.get('embedding_method') == 'CHUNK_AGGREGATED':
                for key in ('fallback', 'direct_failure'):
                    job[key]['node_id'] = job['node_id']
        (self.root / 'provenance.json').write_text(canonical_json({'model_identity': MODEL, 'dimension': 3072,
                                                              'jobs': self.jobs}), encoding='utf-8')
        (self.root / 'chunks.json').write_text(canonical_json({'version': 'boundary_offsets_v1',
            'sources': [job['fallback'] for job in self.jobs if 'fallback' in job], 'source_count': 1}), encoding='utf-8')
        with sqlite3.connect(self.root / 'old-checkpoint.sqlite3') as db:
            db.execute('CREATE TABLE jobs (identity TEXT PRIMARY KEY,state TEXT NOT NULL)')
        paths = {'c3_manifest': str(self.root / 'manifest.json'), 'sample_manifest': str(self.root / 'sample.json'),
            'vector_artifact': str(self.root / 'vectors.jsonl'), 'provenance': str(self.root / 'provenance.json'),
            'chunk_manifest': str(self.root / 'chunks.json'), 'source_checkpoint': str(self.root / 'old-checkpoint.sqlite3'),
            'run_root': str(self.root / 'runs'), 'lock_root': '/run/kag-locks'}
        self.config = dict(scope='C4_3A_MANIFEST_SAMPLE', runtime_location='host',
            endpoints={'openspg': 'http://127.0.0.1:28887', 'neo4j_http': 'http://127.0.0.1:27474',
                       'neo4j_uri': 'bolt://127.0.0.1:27687'}, database='vietroadtraffic', project_id=2,
            project_name='VietRoadTrafficC43A10Pct', namespace='VietRoadTraffic', vector_dimensions=3072,
            confirmation=None, paths=paths, input_sha256={k: checksum(Path(paths[k])) for k in paths
                                                         if k not in ('run_root', 'lock_root')},
            batch_size=2, heartbeat_seconds=5, write_mode='NO_OP', vector_policy='replay-existing',
            model_identity=MODEL, embedding_model=None, fallback_config=self.jobs[1]['fallback_config'],
            credential_env={'neo4j_username': 'TEST_NEO4J_USER', 'neo4j_password': 'TEST_NEO4J_PASSWORD',
                            'embedding_key': 'TEST_EMBEDDING_KEY'})
        self.pins = pins
        self.projects = Projects(self.config['endpoints']['openspg'], [{'id': '2',
            'name': self.config['project_name'], 'namespace': 'VietRoadTraffic'}])
        for target in (patch.object(scope, 'C3_IDENTITY', pins), patch.object(scope, 'ROOT', self.root),
                       patch.object(scope, 'ARTIFACT_HASHES', (('fixture.txt', inputs[0]['sha256']),)),
                       patch.object(self.adapter, '_C43A_POLICY', policy)):
            target.start(); self.addCleanup(target.stop)

    def api(self):
        self.assertTrue((ROOT / 'kag/runner.py').is_file(), 'runner preflight implementation missing')
        return importlib.import_module('kag.runner')

    def preflight(self, config=None, reader=None):
        return self.api().preflight(config or self.config, project_client=self.projects, reader=reader or Database())

    def test_common_c3_validator_has_no_production_authority(self):
        helper = getattr(scope, 'validate_c3_manifest', None)
        self.assertTrue(callable(helper), 'shared data-only C3 validator missing')
        verified = helper(CONTRACT, self.root / 'manifest.json')
        self.assertEqual(verified['nodes'], self.originals)
        self.assertNotIn('settings', verified)
        self.assertNotIn('_proof', verified)

    def test_sample_preflight_binds_real_sdk_scope_and_persisted_source_batches(self):
        api = self.api()
        verified = self.preflight()
        self.assertEqual(verified['writer_config'].scope, 'C4_3A_MANIFEST_SAMPLE')
        self.assertEqual(verified['database_id'], 'physical-fixture-db')
        db_path = self.root / 'planned.sqlite3'
        result = api.plan_sources(self.config, db_path=db_path, verified=verified)
        self.assertEqual((result['nodes'], result['edges']), (3, 1))
        batches = list(api.iter_source_batches(db_path, 'nodes', 2))
        self.assertEqual([len(b) for b in batches], [2, 1])
        self.assertEqual([n for b in batches for n in b], self.originals)
        self.assertTrue(all(not any(k.startswith('_') for k in n['properties']) for b in batches for n in b))

    def test_reordered_source_ledger_cannot_change_resume_batch_boundaries(self):
        api = self.api()
        verified = self.preflight()
        db_path = self.root / 'planned.sqlite3'
        api.plan_sources(self.config, db_path=db_path, verified=verified)
        with sqlite3.connect(db_path) as db:
            db.execute('UPDATE runner_sources SET ordinal=ordinal+100 WHERE kind=\'nodes\'')
            db.execute('UPDATE runner_sources SET ordinal=102-ordinal WHERE kind=\'nodes\'')
        with self.assertRaises(RunBlocked):
            api.plan_sources(self.config, db_path=db_path, verified=verified)

    def test_missing_or_foreign_lock_bind_is_blocked(self):
        api = self.api()
        for mount in ('', '430 421 0:68 /some/other/directory /run/kag-locks rw - 9p D:\\134 rw'):
            with self.subTest(mount=mount), patch('kag.runner.Path.read_text', return_value=mount):
                with self.assertRaises(RunBlocked): api._shared_lock_root('/run/kag-locks')

    def test_deny_unknown_config_secret_endpoints_and_bad_batch_block(self):
        api = self.api()
        for kind in ('DENY', 'unknown', 'secret', 'no-profile', 'bad-batch', 'bool-dimension', 'write-sample'):
            with self.subTest(kind=kind):
                config = copy.deepcopy(self.config)
                if kind == 'DENY': config.pop('scope')
                if kind == 'unknown': config['api_key'] = 'NEVER_LOG_SECRET'
                if kind == 'secret': config['endpoints']['openspg'] = 'http://user:secret@localhost:28887'
                if kind == 'no-profile': config.pop('runtime_location')
                if kind == 'bad-batch': config['batch_size'] = True
                if kind == 'bool-dimension': config['vector_dimensions'] = True
                if kind == 'write-sample': config['write_mode'] = 'WRITE'
                path = self.root / 'config.json'; path.write_text(canonical_json(config), encoding='utf-8')
                with self.assertRaises(RunBlocked): api.load_config(path)

    def test_source_and_artifact_hash_mutations_block_before_discovery(self):
        self.api()
        for field in ('c3_manifest', 'sample_manifest', 'vector_artifact', 'provenance', 'source_checkpoint'):
            with self.subTest(field=field):
                config = copy.deepcopy(self.config); config['input_sha256'][field] = '0' * 64
                before = self.projects.reads
                with self.assertRaises(RunBlocked): self.preflight(config)
                self.assertEqual(self.projects.reads, before)
        (self.root / 'fixture.txt').write_bytes(b'mutated')
        with self.assertRaises(RunBlocked): self.preflight()

    def test_wrong_sample_server_identity_and_database_id_block(self):
        for field, value in (('id', '37'), ('name', 'Production'), ('namespace', 'Foreign')):
            with self.subTest(field=field):
                old = copy.deepcopy(self.projects.records)
                self.projects.records[0][field] = value
                with self.assertRaises(RunBlocked): self.preflight()
                self.projects.records = old
        with self.assertRaises(RunBlocked): self.preflight(reader=Database(None))

    def production(self):
        config = copy.deepcopy(self.config)
        config.update(scope='PRODUCTION', project_id=37, project_name='VietRoadTrafficProduction',
                      write_mode='WRITE', confirmation='CONFIRM_PRODUCTION:VietRoadTrafficProduction:VietRoadTraffic:37:'
                      + self.pins['plan_sha256'])
        self.projects.records = [{'id': '37', 'name': config['project_name'], 'namespace': config['namespace']}]
        return config

    def test_production_resolves_name_namespace_then_binds_expected_id(self):
        verified = self.preflight(self.production())
        self.assertEqual(verified['writer_config'].project_id, 37)
        self.assertEqual(verified['writer_config'].scope, 'PRODUCTION')
        self.assertGreaterEqual(self.projects.reads, 2)

    def test_production_ambiguous_missing_reserved_id_and_confirmation_block(self):
        for kind in ('missing', 'duplicate', 'reserved', 'confirmation'):
            with self.subTest(kind=kind):
                config = self.production()
                if kind == 'missing': self.projects.records.clear()
                if kind == 'duplicate': self.projects.records *= 2
                if kind == 'reserved': config['project_id'] = 2
                if kind == 'confirmation': config['confirmation'] = None
                with self.assertRaises(RunBlocked): self.preflight(config)

    def test_host_and_container_aliases_share_physical_database_lock(self):
        first = self.preflight()
        config = copy.deepcopy(self.config)
        config.update(runtime_location='container')
        config['endpoints']['neo4j_uri'] = 'bolt://openspg-neo4j:7687'
        config['endpoints']['neo4j_http'] = 'http://openspg-neo4j:7474'
        second = self.preflight(config)
        lock = GraphLock(self.config['paths']['lock_root'], first['database_id'], {'run_id': 'first'})
        lock.acquire()
        try:
            with self.assertRaises(RunBlocked):
                GraphLock(config['paths']['lock_root'], second['database_id'], {'run_id': 'second'}).acquire()
        finally:
            lock.release()

    def test_lock_and_run_roots_cannot_overlap_repo_or_old_inputs(self):
        for field, path in (('run_root', ROOT), ('lock_root', ROOT), ('run_root', self.root),
                            ('lock_root', self.root / 'vectors.jsonl'), ('lock_root', self.root / 'other-locks')):
            with self.subTest(field=field, path=path):
                config = copy.deepcopy(self.config); config['paths'][field] = str(path)
                with self.assertRaises(RunBlocked): self.preflight(config)

    def test_official_config_example_defaults_to_deny_without_credentials(self):
        path = ROOT / 'kag/config/runner.example.json'
        self.assertTrue(path.is_file(), 'official runner configuration missing')
        config = json.loads(path.read_bytes())
        self.assertEqual(config['scope'], 'DENY')
        self.assertEqual(config['write_mode'], 'DENY')
        self.assertNotIn('api_key', canonical_json(config))


if __name__ == '__main__':
    unittest.main()
