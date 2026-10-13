"""Synthetic graph fixtures verify inspection gates; never live acceptance."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import httpx
from kag.http_api import artifacts, inspection, runtime
from kag.http_api.app import ApiSettings, create_app
from test_sample_serving import SampleFixture, SECRETS
from kag.evaluation.dataset import canonical_line, freeze_dataset


class SampleInspectionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.fx=SampleFixture(self.root)
        self.settings=runtime.RuntimeSettings(secrets=SECRETS,release_id='synthetic-release',
            source_snapshot_id='synthetic-source',reader_username='sample_reader',reader_password='fixture',sample_proof_sha256=self.fx.pin)
        self.app=create_app(ApiSettings(SECRETS),enable_sample_routes=True)
        self.app.state.serving_release=self.fx.release;self.app.state.runtime_settings=self.settings
        self.app.state.runtime_supervisor=runtime.RuntimeSupervisor()
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://offline')
        self.addAsyncCleanup(self.client.aclose)

    async def get(self,token='i'*43,path='/v1/operations/sample',release='synthetic-release'):
        with patch.object(runtime,'initialize_runtime'),patch.object(runtime,'_new_reader',return_value=self.fx), \
             patch.object(runtime,'_new_embedding',side_effect=AssertionError('egress forbidden')), \
             patch.object(runtime,'_new_llm',side_effect=AssertionError('egress forbidden')):
            return await self.client.get(path,headers={'Authorization':'Bearer '+token,'X-KAG-Release-ID':release})

    async def test_inspect_scope_release_binding_and_arbitrary_query_denied(self):
        for token,status in (('',401),('q'*43,403)):
            self.assertEqual((await self.get(token)).status_code,status)
        self.assertEqual((await self.get(path='/v1/operations/sample?cypher=MATCH')).status_code,422)
        self.assertEqual((await self.get(release='foreign')).status_code,409)

    async def test_actual_nodes_edges_sources_counts_without_vectors_or_credentials(self):
        response=await self.get();self.assertEqual(response.status_code,200,response.text)
        value=response.json();self.assertEqual(value['counts'],{'nodes':3,'edges':1,'vectors':4})
        self.assertEqual(len(value['nodes']),3);self.assertEqual(len(value['edges']),1)
        self.assertEqual(value['graph_fingerprint'],self.fx.binding['graph_fingerprint'])
        node=next(n for n in value['nodes'] if n['entity_id']=='unit-1')
        self.assertEqual(node['properties']['text'],self.fx.nodes[('VietRoadTraffic.LegalUnit','unit-1')]['properties']['text'])
        self.assertEqual(node['sources'][0]['evidence_id'],self.fx.evidence_id)
        self.assertTrue(value['backend']['read_only']);self.assertTrue(value['backend']['verified'])
        self.assertNotIn('_vector',response.text);self.assertNotIn('password',response.text)
        self.assertFalse(value['execution_allowed']);self.assertEqual(value['production_write'],'BLOCKED')
        self.assertTrue(self.fx.closed);self.assertEqual(self.fx.searches,0)

    async def test_graph_drift_and_production_never_become_verified(self):
        self.fx.nodes[('VietRoadTraffic.LegalUnit','unit-1')]['properties']['text']='changed'
        self.assertEqual((await self.get()).status_code,503)
        self.app.state.serving_release=replace(self.fx.release,release_kind='PRODUCTION')
        self.assertEqual((await self.get()).status_code,503)

    async def test_missing_release_or_pin_fail_closed(self):
        self.app.state.runtime_settings=replace(self.settings,sample_proof_sha256=None)
        self.assertEqual((await self.get()).status_code,503)
        self.app.state.serving_release=None
        self.assertEqual((await self.get()).status_code,503)


class SampleDatasetReadinessTests(unittest.TestCase):
    def test_frozen_dataset_report_view_is_not_limited_to_three_questions(self):
        from kag.evaluation.dataset import load_dataset,sha256
        from kag.evaluation.models import EvaluationProtocol
        from kag.evaluation.evaluate import evaluate_g1
        source=self.root/'reviewed.jsonl'
        source.write_bytes(b''.join(canonical_line(self.record(str(i),'unit-1')) for i in range(5)))
        manifest=freeze_dataset(source,self.datasets,'reviewed-synthetic')
        file=manifest.with_name('eval_questions.jsonl');dataset=load_dataset(file)
        class Retriever:
            search_k=1
            def retrieve(self,*args,**kwargs):return []
        evaluate_g1(dataset,Retriever(),EvaluationProtocol(ks=(1,),top_k=1,release_id=self.fx.release.release_id),output_dir=file.parent/'G1')
        (file.parent/'sample-smoke.json').write_bytes(canonical_line(dict(schema_version='1.0',dataset_hash=dataset.dataset_hash,
            graph_fingerprint=self.fx.release.descriptor['graph_fingerprint'],source_catalog_sha256=self.fx.release.descriptor['source_catalog_sha256'],
            review_status='FROZEN',runs={'G1':sha256((file.parent/'G1/run_manifest.json').read_bytes()),'G2':None})))
        value=inspection.dataset_readiness(self.datasets,self.fx.release);row=value['datasets'][0]
        self.assertEqual(row['smoke']['state'],'AVAILABLE')
        self.assertEqual(row['smoke']['review_status'],'FROZEN')
        self.assertEqual(row['smoke']['runs']['G1']['requested_count'],5)
        self.assertFalse(value['execution_allowed']);self.assertFalse(row['official_benchmark'])

    def test_dataset_metadata_categories_and_protocol_configuration(self):
        from kag.evaluation.dataset import dataset_from_records,sha256
        from kag.evaluation.models import EvaluationProtocol
        from kag.evaluation.evaluate import evaluate_g1
        folder=self.datasets/'sample';folder.mkdir();payload=self.record('one','unit-1')
        (folder/'eval_questions.jsonl').write_bytes(canonical_line(payload));dataset=dataset_from_records([payload])
        class Retriever:
            search_k=1
            def retrieve(self,*args,**kwargs):return []
        protocol=EvaluationProtocol(ks=(1,),top_k=1,release_id=self.fx.release.release_id,metric_policy_version='1.1')
        evaluate_g1(dataset,Retriever(),protocol,output_dir=folder/'G1')
        (folder/'sample-smoke.json').write_bytes(canonical_line(dict(schema_version='1.0',dataset_hash=dataset.dataset_hash,
            graph_fingerprint=self.fx.release.descriptor['graph_fingerprint'],source_catalog_sha256=self.fx.release.descriptor['source_catalog_sha256'],
            review_status='PROVISIONAL',runs={'G1':sha256((folder/'G1/run_manifest.json').read_bytes()),'G2':None})))
        row=inspection.dataset_readiness(self.datasets,self.fx.release)['datasets'][0]
        self.assertEqual(row['metadata']['dataset_version'],'synthetic')
        self.assertEqual(row['metadata']['category_counts'],{'definition':1})
        self.assertEqual(row['smoke']['runs']['G1']['configuration'],protocol.to_dict())
        self.assertFalse(row['official_benchmark'])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'release').mkdir();self.fx=SampleFixture(self.root/'release')
        self.datasets=self.root/'datasets';self.datasets.mkdir()

    def record(self,qid,unit):
        return dict(schema_version='1.0',dataset_version='synthetic',dataset_status='PROVISIONAL',qid=qid,
            question='TEST ONLY',category='definition',expected_abstain=False,gold_unit_ids=[unit])

    def test_frozen_coverage_counts_missing_gold_and_null_metrics(self):
        file=self.datasets/'source.jsonl'
        file.write_bytes(canonical_line(self.record('one','unit-1'))+canonical_line(self.record('two','outside')))
        freeze_dataset(file,self.datasets,'synthetic-frozen')
        value=inspection.dataset_readiness(self.datasets,self.fx.release)
        row=next(r for r in value['datasets'] if r['id'].endswith('/eval_questions.jsonl'))
        self.assertEqual((row['eligible_count'],row['ineligible_count'],row['invalid_count'],row['gold_count']),(1,1,0,2))
        self.assertEqual(row['missing_gold'],{'document':[],'unit':['outside'],'sign':[]})
        self.assertIsNone(value['metrics']);self.assertFalse(value['execution_allowed'])

    def test_provisional_does_not_claim_frozen_benchmark_and_legacy_is_invalid(self):
        (self.datasets/'provisional.jsonl').write_bytes(canonical_line(self.record('one','unit-1')))
        (self.datasets/'legacy.jsonl').write_text('{"id":"Q001","cau_hoi":"TEST ONLY","gold_unit_ids":["outside"]}\n',encoding='utf-8')
        value=inspection.dataset_readiness(self.datasets,self.fx.release);rows={r['id']:r for r in value['datasets']}
        self.assertEqual((rows['provisional.jsonl']['eligible_count'],rows['provisional.jsonl']['reason']),(0,'PROVISIONAL_DATASET'))
        self.assertEqual((rows['legacy.jsonl']['record_count'],rows['legacy.jsonl']['invalid_count'],rows['legacy.jsonl']['eligible_count']),(1,1,0))
        self.assertEqual(rows['legacy.jsonl']['missing_gold']['unit'],['outside'])
        self.assertEqual(rows['legacy.jsonl']['reason'],'INVALID_DATASET')

    def test_inspection_does_not_change_dataset_or_graph(self):
        file=self.datasets/'source.jsonl';raw=canonical_line(self.record('one','outside'));file.write_bytes(raw)
        inspection.dataset_readiness(self.datasets,self.fx.release)
        self.assertEqual(file.read_bytes(),raw)

    def test_provisional_smoke_eligibility_does_not_authorize_official_execution(self):
        file=self.datasets/'source.jsonl'
        file.write_bytes(canonical_line(self.record('one','unit-1')))
        row=inspection.dataset_readiness(self.datasets,self.fx.release)['datasets'][0]
        self.assertIn('smoke',row)
        self.assertEqual(row['smoke']['g1_eligible_count'],1)
        self.assertEqual(row['smoke']['review_status'],'PROVISIONAL')
        self.assertEqual(row['smoke']['state'],'NOT_RUN')
        self.assertIsNone(row['smoke']['runs']['G1'])
        self.assertEqual(row['dataset_eligibility'],'BLOCKED')

    def test_smoke_receipt_requires_matching_graph_dataset_and_framework_hashes(self):
        from kag.evaluation.dataset import dataset_from_records, sha256
        from kag.evaluation.models import EvaluationProtocol
        from kag.evaluation.evaluate import evaluate_g1
        folder=self.datasets/'sample';folder.mkdir()
        payload=self.record('one','unit-1');file=folder/'eval_questions.jsonl';file.write_bytes(canonical_line(payload))
        dataset=dataset_from_records([payload])
        class Retriever:
            search_k=1
            def retrieve(self,*args,**kwargs): return []
        protocol=EvaluationProtocol(ks=(1,),top_k=1,release_id=self.fx.release.release_id)
        evaluate_g1(dataset,Retriever(),protocol,output_dir=folder/'G1')
        receipt=dict(schema_version='1.0',dataset_hash=dataset.dataset_hash,
            graph_fingerprint=self.fx.release.descriptor['graph_fingerprint'],
            source_catalog_sha256=self.fx.release.descriptor['source_catalog_sha256'],
            review_status='PROVISIONAL',runs={'G1':sha256((folder/'G1/run_manifest.json').read_bytes()),'G2':None})
        (folder/'sample-smoke.json').write_bytes(canonical_line(receipt))
        def view():return inspection.dataset_readiness(self.datasets,self.fx.release)['datasets'][0]['smoke']
        row=inspection.dataset_readiness(self.datasets,self.fx.release)['datasets'][0];self.assertIn('smoke',row)
        smoke=view();self.assertEqual(smoke['state'],'AVAILABLE');self.assertEqual(smoke['runs']['G1']['attempted_count'],1)
        self.assertEqual(smoke['runs']['G1']['metrics']['unit.Hit@1']['value'],0)
        self.assertFalse(smoke['official_benchmark'])
        (folder/'G1/metrics.json').write_bytes(b'{}')
        self.assertEqual(view()['state'],'INVALID_RECEIPT');self.assertIsNone(view()['runs']['G1'])
        receipt['graph_fingerprint']='0'*64;(folder/'sample-smoke.json').write_bytes(canonical_line(receipt))
        self.assertEqual(view()['state'],'INVALID_RECEIPT')

    def test_malformed_receipt_collection_does_not_break_sample_inspection(self):
        from kag.evaluation.dataset import dataset_from_records
        folder=self.datasets/'sample';folder.mkdir();payload=self.record('one','unit-1')
        (folder/'eval_questions.jsonl').write_bytes(canonical_line(payload))
        receipt=dict(schema_version='1.0',dataset_hash=dataset_from_records([payload]).dataset_hash,
            graph_fingerprint=self.fx.release.descriptor['graph_fingerprint'],
            source_catalog_sha256=self.fx.release.descriptor['source_catalog_sha256'],review_status='PROVISIONAL',runs=['G1','G2'])
        (folder/'sample-smoke.json').write_bytes(canonical_line(receipt))
        row=inspection.dataset_readiness(self.datasets,self.fx.release)['datasets'][0]
        self.assertEqual(row['smoke']['state'],'INVALID_RECEIPT')
        self.assertEqual(row['smoke']['runs'],{'G1':None,'G2':None})
