"""SYNTHETIC ASGI query/release, real native Core for integration cases, no I/O."""
import asyncio
from contextlib import AsyncExitStack, contextmanager
import copy
from dataclasses import replace
from datetime import datetime, timedelta
import io
import json
import logging
import threading
import unittest
from unittest.mock import patch
from uuid import UUID

import httpx
import test_runtime as native
from kag.http_api.app import ApiSettings, create_app
from kag.http_api import artifacts, contract, runtime, security
from kag.legal_solver import AnswerResult, Citation
OPERATIONAL_PROOF = runtime._require_operational_proof


class AppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fixture = native.RuntimeTests()
        await self.fixture.asyncSetUp()
        self.reader, self.release = self.fixture.reader, self.fixture.release
        self.stack = AsyncExitStack()
        self.stack.enter_context(self.fixture.synthetic())
        self.made = []
        def factory(*args):
            value = runtime.make_runtime(*args)
            self.made.append(value)
            return value
        self.app = create_app(ApiSettings(native.SECRETS),runtime_factory=factory)
        # Only tests install synthetic authorities; normal app has none.
        self.app.state.serving_release = self.release
        self.app.state.runtime_settings = self.fixture.settings()
        await self.stack.enter_async_context(self.app.router.lifespan_context(self.app))
        self.client = await self.stack.enter_async_context(httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),base_url='http://asgi.invalid'))
        self.supervisor = self.app.state.runtime_supervisor

    async def asyncTearDown(self):
        await self.stack.aclose()
        await self.fixture.asyncTearDown()

    def headers(self, **changes):
        return {'Authorization':'Bearer '+'q'*43,'Content-Type':'application/json',
            'X-KAG-Release-ID':'synthetic-release','X-WebApp-Snapshot-ID':'synthetic-webapp',
            'X-KAG-As-Of':native.AS_OF.isoformat(),**changes}

    def body(self, **changes):
        return {'user_id':native.USER,'message':native.QUESTION,'context_id':'',
            'schema_contract':native.IDENTITY,**changes}

    async def post(self, *, body=None, headers=None, raw=None, path='/v1/query'):
        return await self.client.post(path,headers=self.headers() if headers is None else headers,
            content=json.dumps(self.body() if body is None else body).encode() if raw is None else raw)

    def error(self, response, status, code, state=None):
        self.assertEqual(response.status_code,status,response.text)
        body = response.json()
        self.assertEqual(set(body),{'request_id','error','native_state'})
        self.assertEqual(set(body['error']),{'code','message','retryable'})
        self.assertEqual(body['error']['code'],code)
        self.assertEqual(body['native_state'],state)
        self.assertEqual(str(UUID(body['request_id'])),body['request_id'])
        self.assertEqual(response.headers['x-request-id'],body['request_id'])
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertLessEqual(len(response.content),4096)
        self.assertNotIn('citations',body)
        self.assertNotIn('answer',body)

    def citation(self, kind='LegalUnit', field='text', identity='unit-1'):
        record = next(r for r in self.app.state.serving_release.records
            if r.entity_type=='VietRoadTraffic.'+kind and r.entity_id==identity and r.field==field)
        return Citation(record.doc_id,record.unit_id,record.sign_id,record.evidence_id,
                        record.field,0,len(record.source_text),record.source_text)

    @contextmanager
    def result(self, value):
        """Typed edge fixtures at the native-return boundary, never production code."""
        async def call(*args):
            return value
        with patch.object(runtime,'run_query',call):
            yield

    @contextmanager
    def after_core(self, mutate):
        original = runtime.run_query
        async def call(*args):
            value = await original(*args)
            mutate()
            return value
        with patch.object(runtime,'run_query',call):
            yield

    def reload(self):
        self.reader.seal()
        self.release = artifacts.load_release(self.fixture.root,'synthetic-release')
        self.app.state.serving_release = self.release

    def units(self, text, count=1):
        row = self.reader.nodes['VietRoadTraffic.LegalUnit','unit-1']
        record = next(r for r in self.reader.catalog['records'] if r['entity_type'].endswith('.LegalUnit'))
        row['properties']['text'] = text
        record.update(source_text=text,source_sha256=native.sha(text.encode()))
        record['metadata']['text'] = text
        self.reader.publication['units'][0]['text_sha256'] = native.sha(text.encode())
        for number in range(2,count+1):
            identity = 'unit-'+str(number)
            node = copy.deepcopy(row)
            node['properties'].update(id=identity,name=identity)
            self.reader.nodes['VietRoadTraffic.LegalUnit',identity] = node
            item = copy.deepcopy(record)
            item.update(entity_id=identity,unit_id=identity,graph_context=[])
            item['metadata'].update(id=identity,name=identity)
            self.reader.catalog['records'].append(item)
            self.reader.publication['units'].append({'doc_id':'document-1','unit_id':identity,
                'text_sha256':native.sha(text.encode()),'published':True,'version':'synthetic-v1'})
        self.reload()
        return tuple(self.citation(identity='unit-'+str(i)) for i in range(1,count+1))

    async def test_real_native_answer_exact_v1_and_identity_echoes(self):
        response = await self.post()
        self.assertEqual(response.status_code,200,response.text)
        citation = self.citation()
        self.assertEqual(response.json(),{'answer':'Căn cứ nguồn đã xác nhận:\n'+native.TEXT,
            'citations':[{'doc_id':'document-1','unit_id':'unit-1','sign_id':None,
                'evidence_id':citation.evidence_id,'field':'text','start':0,'end':len(native.TEXT),'quote':native.TEXT}]})
        self.assertEqual(response.headers['x-kag-release-id'],'synthetic-release')
        self.assertEqual(response.headers['x-webapp-snapshot-id'],'synthetic-webapp')
        self.assertEqual(response.headers['x-kag-as-of'],'2026-10-08')
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertTrue(self.reader.closed and self.made[0].closed)
        self.assertFalse(self.supervisor.busy)

    async def test_real_native_abstention_never_becomes_success(self):
        with self.fixture.synthetic(abstain=True):
            response = await self.post()
        self.error(response,503,'KAG_ABSTAINED','abstained')
        self.assertTrue(self.reader.closed)

    async def test_missing_bearer_before_factory(self):
        headers = self.headers(); headers.pop('Authorization')
        self.error(await self.post(headers=headers),401,'AUTH_REQUIRED')
        self.assertEqual(self.made,[])

    async def test_invalid_bearer_before_factory(self):
        for token in ('Basic x','Bearer invalid','Bearer '+('q'*43)+' extra'):
            with self.subTest(token=token):
                self.error(await self.post(headers=self.headers(Authorization=token)),401,'AUTH_INVALID')
        self.assertEqual(self.made,[])

    async def test_wrong_scope_before_factory(self):
        self.error(await self.post(headers=self.headers(Authorization='Bearer '+'i'*43)),403,'SCOPE_DENIED')
        self.assertEqual(self.made,[])

    async def test_delegation_denied_before_factory(self):
        principal = security.ServicePrincipal('query-no-delegation',frozenset({'query'}),False)
        with patch.object(security,'authenticate',return_value=principal):
            self.error(await self.post(),403,'DELEGATION_DENIED')
        self.assertEqual(self.made,[])

    async def test_forged_identity_header_rejected(self):
        self.error(await self.post(headers=self.headers(**{'X-User-ID':native.USER})),422,'INVALID_REQUEST')
        self.assertEqual(self.made,[])

    async def test_json_duplicate_nonfinite_bom_surrogate_utf8_rejected(self):
        for raw in (b'{"user_id":1,"user_id":2}',b'{"x":NaN}',b'{"x":Infinity}',
                    b'\xef\xbb\xbf{}',b'{"x":"\\ud800"}',b'\xff',b'not-json'):
            with self.subTest(raw=raw):
                self.error(await self.post(raw=raw),400,'INVALID_JSON')
        self.assertEqual(self.made,[])

    async def test_unknown_uuid_and_type_fields_rejected(self):
        for body in (self.body(write=True),self.body(user_id='not-uuid'),self.body(message=1),
                     self.body(context_id=None),self.body(as_of='2020-01-01')):
            with self.subTest(body=body):
                self.error(await self.post(body=body),422,'INVALID_REQUEST')
        self.assertEqual(self.made,[])

    async def test_context_rejected_without_core_session_fallback(self):
        self.error(await self.post(body=self.body(context_id='session')),422,'CONTEXT_NOT_SUPPORTED')
        self.assertEqual(self.made,[])

    async def test_unsupported_media_and_encoding(self):
        for changes in ({'Content-Type':'text/plain'},{'Content-Type':'application/json; charset=utf-16'},
                        {'Content-Encoding':'gzip'}):
            with self.subTest(changes=changes):
                self.error(await self.post(headers=self.headers(**changes)),415,'UNSUPPORTED_MEDIA_TYPE')
        self.assertEqual(self.made,[])

    async def test_oversized_streamed_body_before_factory(self):
        async def chunks():
            yield b' '*65536
            yield b' '
        self.error(await self.post(raw=chunks()),413,'REQUEST_TOO_LARGE')
        self.assertEqual(self.made,[])

    async def test_strict_dto_single_path(self):
        original = contract.QueryV1Request.from_json
        with patch.object(contract.QueryV1Request,'from_json',wraps=original) as parser:
            response = await self.post(raw=b'{"user_id":1,"user_id":2}')
        self.error(response,400,'INVALID_JSON')
        self.assertEqual(parser.call_count,1)
        self.assertEqual(self.made,[])

    async def test_schema_mismatch_before_factory(self):
        self.error(await self.post(body=self.body(schema_contract={**native.IDENTITY,'schema_sha256':'f'*64})),
                   409,'SCHEMA_CONTRACT_MISMATCH')
        self.assertEqual(self.made,[])

    async def test_release_snapshot_date_headers_before_factory(self):
        for key,value,code in (('X-KAG-Release-ID','foreign','RELEASE_MISMATCH'),
            ('X-WebApp-Snapshot-ID','foreign','SOURCE_SNAPSHOT_MISMATCH'),
            ('X-KAG-As-Of','2000-01-01','DATE_MISMATCH')):
            with self.subTest(key=key):
                self.error(await self.post(headers=self.headers(**{key:value})),409,code)
        self.assertEqual(self.made,[])

    async def test_missing_release_unavailable(self):
        self.app.state.serving_release = None
        self.error(await self.post(),503,'RELEASE_UNAVAILABLE')
        self.assertEqual(self.made,[])

    async def test_missing_publication_unavailable(self):
        self.app.state.serving_release = replace(self.release,publication=None)
        self.error(await self.post(),503,'NOT_READY')
        self.assertEqual(self.made,[])

    async def test_default_operational_proof_still_denies_synthetic(self):
        with patch.object(runtime,'_require_operational_proof',OPERATIONAL_PROOF):
            self.error(await self.post(),503,'NOT_READY')
        self.assertEqual(self.made,[])

    async def test_normal_app_without_injection_cannot_serve(self):
        app = create_app(ApiSettings(native.SECRETS))
        async with app.router.lifespan_context(app),httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),base_url='http://asgi.invalid') as client:
            response = await client.post('/v1/query',headers=self.headers(),content=json.dumps(self.body()).encode())
        self.error(response,503,'RELEASE_UNAVAILABLE')

    async def test_sign_native_support_cannot_become_unit(self):
        value = AnswerResult('Nguồn biển báo.',(self.citation('TrafficSign','moTa','sign-1'),),False)
        before = value.to_dict()
        with self.result(value):
            self.error(await self.post(),503,'V1_RESULT_UNREPRESENTABLE','answered')
        self.assertEqual(value.to_dict(),before)

    async def test_document_native_support_unrepresentable(self):
        value = AnswerResult('Nguồn văn bản.',(self.citation('LegalDocument','title','document-1'),),False)
        with self.result(value):
            self.error(await self.post(),503,'V1_RESULT_UNREPRESENTABLE','answered')

    async def test_mixed_metadata_all_support_preserved_and_refused(self):
        value = AnswerResult('Nguồn gồm metadata.',(self.citation(),
            self.citation('LegalDocument','effective_from','document-1')),False)
        before = value.to_dict()
        with self.result(value):
            self.error(await self.post(),503,'V1_RESULT_UNREPRESENTABLE','answered')
        self.assertEqual(value.to_dict(),before)

    async def test_invalid_citation_source_ids_quote_and_spans(self):
        original = self.citation()
        for changes in ({'unit_id':'foreign'},{'doc_id':'foreign'},{'evidence_id':'a'*64},
                        {'quote':'forged'},{'start':True},{'start':1},{'end':original.end-1}):
            with self.subTest(changes=changes),self.result(AnswerResult('Nguồn.',(replace(original,**changes),),False)):
                self.reader.closed = False
                self.error(await self.post(),502,'SOURCE_VALIDATION_FAILED')

    async def test_invalid_native_shape_no_guessed_state(self):
        with self.result({'answer':'fake','citations':[]}):
            self.error(await self.post(),502,'INVALID_NATIVE_RESULT')

    async def test_changed_source_after_actual_core_fails_final_proof(self):
        with self.after_core(lambda:self.reader.nodes['VietRoadTraffic.LegalUnit','unit-1']['properties'].update(text='changed')):
            self.error(await self.post(),502,'SOURCE_VALIDATION_FAILED')
        self.assertTrue(self.reader.closed)

    async def test_changed_graph_relation_after_core_fails(self):
        with self.after_core(lambda:self.reader.edges.clear()):
            self.error(await self.post(),502,'SOURCE_VALIDATION_FAILED')

    async def test_changed_backend_after_core_fails(self):
        with self.after_core(lambda:self.reader.metadata.update(databaseID='foreign')):
            self.error(await self.post(),502,'SOURCE_VALIDATION_FAILED')

    async def test_changed_index_after_core_fails(self):
        with self.after_core(lambda:self.reader.vector_indexes[0].update(state='POPULATING')):
            self.error(await self.post(),502,'SOURCE_VALIDATION_FAILED')

    async def test_source_catalog_tamper_after_core_fails(self):
        with self.after_core(lambda:(self.fixture.root/'source-catalog.json').write_bytes(b'{}')):
            self.error(await self.post(),502,'SOURCE_VALIDATION_FAILED')

    async def test_release_artifact_changed_after_core_conflict(self):
        with self.after_core(lambda:(self.fixture.root/'release.json').write_bytes(b'{}')):
            self.error(await self.post(),409,'RELEASE_MISMATCH')

    async def test_selected_schema_changed_after_core_conflict(self):
        changed = replace(self.release,schema_contract=contract.SchemaIdentity('VietRoadTraffic','f'*64,'b'*64))
        with self.after_core(lambda:setattr(self.app.state,'serving_release',changed)):
            self.error(await self.post(),409,'SCHEMA_CONTRACT_MISMATCH')

    async def test_selected_snapshot_changed_after_core_conflict(self):
        descriptor = dict(self.release.descriptor,source_snapshot_id='foreign')
        changed = replace(self.release,descriptor=descriptor)
        with self.after_core(lambda:setattr(self.app.state,'serving_release',changed)):
            self.error(await self.post(),409,'SOURCE_SNAPSHOT_MISMATCH')

    async def test_publication_tamper_after_core_fails(self):
        with self.after_core(lambda:(self.fixture.root/'webapp-publication.json').write_bytes(b'{}')):
            self.error(await self.post(),502,'SOURCE_VALIDATION_FAILED')

    async def test_unpublished_or_replaced_authority_unrepresentable(self):
        self.reader.publication['documents'][0]['replaces_eligible'] = False
        self.reload()
        self.error(await self.post(),503,'V1_RESULT_UNREPRESENTABLE','answered')

    async def test_effectivity_rejected_before_projection(self):
        # Legitimate immutable fixture at current date; typed result cites expired source.
        self.reader.nodes['VietRoadTraffic.LegalDocument','document-1']['properties']['effectiveTo'] = '2020-12-31'
        for record in self.reader.catalog['records']:
            if record['entity_type'].endswith('.LegalDocument'):
                record['metadata']['effective_to'] = '2020-12-31'
        self.reader.publication['documents'][0]['effective_to'] = '2020-12-31'
        self.reload()
        with self.result(AnswerResult('Nguồn.',(self.citation(),),False)):
            self.error(await self.post(),502,'SOURCE_VALIDATION_FAILED')

    async def test_midnight_after_core_aborts_without_success(self):
        with self.after_core(lambda:self.stack.enter_context(patch.object(runtime,'_today',lambda:native.AS_OF+timedelta(days=1)))):
            self.error(await self.post(),409,'DATE_BOUNDARY_CHANGED')

    async def test_midnight_during_serialization_aborts(self):
        original = contract.encode_v1
        def encode(value):
            result = original(value)
            self.stack.enter_context(patch.object(runtime,'_today',lambda:native.AS_OF+timedelta(days=1)))
            return result
        with patch.object(contract,'encode_v1',encode):
            self.error(await self.post(),409,'DATE_BOUNDARY_CHANGED')

    async def test_answer_utf16_exact_limit_and_overflow(self):
        for count,status in ((10000,200),(10001,503)):
            value = AnswerResult('😀'*count,(self.citation(),),False)
            with self.subTest(count=count),self.result(value):
                self.reader.closed = False
                response = await self.post()
                if status == 200:
                    self.assertEqual(response.status_code,200,response.text)
                    self.assertEqual(response.json()['answer'],value.answer)
                else:
                    self.error(response,503,'V1_RESULT_UNREPRESENTABLE','answered')

    async def test_quote_utf16_limit_refuses_whole_result(self):
        citations = self.units('😀'*10001)
        with self.result(AnswerResult('Nguồn.',citations,False)):
            self.error(await self.post(),503,'V1_RESULT_UNREPRESENTABLE','answered')

    async def test_citation_count_limit_refuses_whole_result(self):
        citations = self.units(native.TEXT,21)
        with self.result(AnswerResult('Nguồn.',citations,False)):
            self.error(await self.post(),503,'V1_RESULT_UNREPRESENTABLE','answered')

    async def test_wire_byte_limit_502_without_truncation(self):
        citations = self.units('法'*20000,8)
        value = AnswerResult('Nguồn.',citations,False)
        before = value.to_dict()
        with self.result(value):
            self.error(await self.post(),502,'RESULT_LIMIT_EXCEEDED')
        self.assertEqual(value.to_dict(),before)

    async def test_native_answer_and_as_of_forwarded_unchanged(self):
        seen = []
        original = runtime.run_query
        async def call(instance,question,as_of):
            seen.append((question,as_of))
            return await original(instance,question,as_of)
        message = ' '+native.QUESTION+' '
        with patch.object(runtime,'run_query',call):
            response = await self.post(body=self.body(message=message))
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(seen,[(message,native.AS_OF)])

    async def test_provider_error_sanitized(self):
        async def call(*args):
            raise runtime.RuntimeFailure('PROVIDER_ERROR')
        with patch.object(runtime,'run_query',call):
            self.error(await self.post(),502,'PROVIDER_ERROR')

    async def test_unexpected_exception_no_secret_or_trace_in_output_logs(self):
        secret = 'synthetic-secret-do-not-log'
        async def call(*args):
            raise RuntimeError(secret)
        stream = io.StringIO(); handler = logging.StreamHandler(stream)
        logging.getLogger().addHandler(handler)
        try:
            with patch.object(runtime,'run_query',call):
                response = await self.post()
        finally:
            logging.getLogger().removeHandler(handler)
        self.error(response,500,'INTERNAL_ERROR')
        self.assertNotIn(secret,response.text+stream.getvalue())
        self.assertNotIn('Traceback',response.text+stream.getvalue())

    async def test_missing_backend_after_core_unavailable(self):
        def mutate():
            self.stack.enter_context(patch.object(self.reader,'database_metadata',side_effect=RuntimeError('synthetic-secret')))
        with self.after_core(mutate):
            self.error(await self.post(),503,'BACKEND_UNAVAILABLE')

    @contextmanager
    def blocked_core(self, entered, finish):
        original = runtime._new_llm
        def model(*args):
            base = type(original(*args))
            class BlockingLLM(base):
                def __call__(self,*arguments,**kwargs):
                    if not entered.is_set():
                        entered.set()
                        if not finish.wait(5):
                            raise AssertionError('Test must release synthetic SDK worker')
                    return super().__call__(*arguments,**kwargs)
            return BlockingLLM()
        with patch.object(runtime,'_new_llm',model):
            yield

    async def test_http_timeout_contention_and_long_worker_drain(self):
        entered,finish = threading.Event(),threading.Event()
        with self.blocked_core(entered,finish),patch.object(runtime,'REQUEST_SECONDS',1):
            task = asyncio.create_task(self.post())
            try:
                while not entered.is_set() and not task.done():
                    await asyncio.sleep(.001)
                self.assertTrue(entered.is_set())
                self.error(await task,504,'QUERY_TIMEOUT')
                self.assertTrue(self.supervisor.busy and self.supervisor.draining)
                self.assertFalse(self.reader.closed)
                response = await self.post()
                self.error(response,429,'CONCURRENCY_LIMIT')
                self.assertEqual(response.headers['retry-after'],'1')
                self.assertEqual((await self.client.get('/v1/health')).status_code,200)
            finally:
                finish.set()
                await self.supervisor.close()
        self.assertTrue(self.reader.closed)
        self.assertFalse(self.supervisor.busy)

    async def test_http_handler_cancel_keeps_owned_worker_until_drain(self):
        entered,finish = threading.Event(),threading.Event()
        with self.blocked_core(entered,finish):
            task = asyncio.create_task(self.post())
            try:
                while not entered.is_set() and not task.done():
                    await asyncio.sleep(.001)
                self.assertTrue(entered.is_set())
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertTrue(self.supervisor.busy and self.supervisor.draining)
                self.assertFalse(self.reader.closed)
            finally:
                finish.set()
                await self.supervisor.close()
        self.assertTrue(self.reader.closed)
        self.assertFalse(self.supervisor.busy)

    async def test_timeout_during_final_readback_holds_reader_and_no_success(self):
        entered,finish = threading.Event(),threading.Event()
        done_core = threading.Event()
        original = self.reader.read_nodes
        def read(keys):
            if done_core.is_set():
                entered.set()
                if not finish.wait(5):
                    raise AssertionError('Test must release final proof')
            return original(keys)
        with self.after_core(done_core.set),patch.object(self.reader,'read_nodes',read),patch.object(runtime,'REQUEST_SECONDS',1):
            task = asyncio.create_task(self.post())
            try:
                while not entered.is_set() and not task.done():
                    await asyncio.sleep(.001)
                self.assertTrue(entered.is_set())
                self.error(await task,504,'QUERY_TIMEOUT')
                self.assertTrue(self.supervisor.busy)
                self.assertFalse(self.reader.closed)
            finally:
                finish.set()
                await self.supervisor.close()
        self.assertTrue(self.reader.closed)

    async def test_readiness_stays_unavailable_after_positive_query(self):
        self.assertEqual((await self.post()).status_code,200)
        response = await self.client.get('/v1/health?mode=ready&capability=query-v1',headers=self.headers())
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json()['checks']['runtime'],'blocked')
        self.assertEqual(response.json()['provider_transport'],'not_probed')

    async def test_graph_release_artifact_view_no_live_claims(self):
        response = await self.client.get('/v1/graph/release',headers=self.headers())
        self.assertEqual(response.status_code,200,response.text)
        value = response.json()
        self.assertEqual(value['release_id'],'synthetic-release')
        self.assertEqual(value['release_kind'],'SAMPLE')
        self.assertFalse(value['backend_identity_verified'] or value['source_identity_verified'] or value['query_ready'])
        self.assertIsNone(value['verified_at'])
        self.assertEqual(self.made,[])
        self.assertEqual(self.fixture.events,[])

    async def test_graph_release_missing_or_tampered_unavailable(self):
        self.app.state.serving_release = None
        self.error(await self.client.get('/v1/graph/release',headers=self.headers()),503,'RELEASE_UNAVAILABLE')
        self.app.state.serving_release = self.release
        (self.fixture.root/'release.json').write_bytes(b'{}')
        self.error(await self.client.get('/v1/graph/release',headers=self.headers()),503,'RELEASE_UNAVAILABLE')

    async def test_graph_release_auth_and_query_selector_rejection(self):
        self.error(await self.client.get('/v1/graph/release'),401,'AUTH_REQUIRED')
        self.error(await self.client.get('/v1/graph/release?run_id=foreign',headers=self.headers()),422,'INVALID_REQUEST')
        response = await self.client.get('/v1/graph/release',headers=self.headers(Authorization='Bearer '+'i'*43))
        self.assertEqual(response.status_code,200)

    async def test_only_step5_approved_public_routes_and_methods(self):
        paths = self.app.openapi()['paths']
        self.assertEqual(set(paths),{'/v1/health','/v1/graph/release','/v1/query'})
        self.assertEqual(set(paths['/v1/query']),{'post'})
        for path in ('/v1/query/stream','/v1/retrieve','/v1/jobs','/v1/benchmarks','/v2/query','/write','/docs','/openapi.json'):
            self.assertEqual((await self.client.post(path)).status_code,404)

    async def test_query_unknown_url_options_rejected_before_factory(self):
        self.error(await self.post(path='/v1/query?model=foreign'),422,'INVALID_REQUEST')
        self.assertEqual(self.made,[])

    async def test_server_generated_request_id_cannot_be_forged(self):
        response = await self.post(headers=self.headers(**{'X-Request-ID':'forged'}))
        self.assertEqual(response.status_code,200,response.text)
        self.assertNotEqual(response.headers['x-request-id'],'forged')
        self.assertEqual(str(UUID(response.headers['x-request-id'])),response.headers['x-request-id'])

    async def test_disconnect_probe_swallowed_cancellation_cannot_hold_response(self):
        swallowed = asyncio.Event()
        async def probe(request):
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                if swallowed.is_set():
                    raise
                swallowed.set()
            return False
        with patch('starlette.requests.Request.is_disconnected',probe):
            task = asyncio.create_task(self.post())
            done,_ = await asyncio.wait({task},timeout=3)
            if not done:
                task.cancel()
                await asyncio.gather(task,return_exceptions=True)
            self.assertTrue(done,'Disconnect probe swallowed cancellation and held response')
            self.assertEqual(task.result().status_code,200)
            self.assertTrue(swallowed.is_set())

    async def test_unconfigured_secret_policy_remains_liveness_only(self):
        app = create_app(ApiSettings())
        self.assertEqual({route.path for route in app.routes},{'/v1/health'})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://asgi.invalid') as client:
            self.assertEqual((await client.post('/v1/query')).status_code,404)
            self.assertEqual((await client.get('/v1/graph/release')).status_code,404)

    async def raw_asgi(self, send=None, disconnect=None):
        body = json.dumps(self.body()).encode()
        headers = {**self.headers(),'Content-Length':str(len(body))}
        scope = {'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','scheme':'http',
            'method':'POST','path':'/v1/query','raw_path':b'/v1/query','query_string':b'',
            'root_path':'','headers':[(k.lower().encode(),v.encode()) for k,v in headers.items()],
            'server':('asgi.invalid',80),'client':('127.0.0.1',1234)}
        received = False
        messages = []
        async def receive():
            nonlocal received
            if not received:
                received = True
                return {'type':'http.request','body':body,'more_body':False}
            if disconnect is None:
                await asyncio.Future()
            else:
                await disconnect.wait()
            return {'type':'http.disconnect'}
        async def capture(message):
            if send is not None:
                await send(message)
            messages.append(dict(message))
        await self.app(scope,receive,capture)
        return messages

    async def test_midnight_in_preflight_denies_factory_and_public_inference(self):
        original = runtime._readback
        def readback(*args):
            value = original(*args)
            self.stack.enter_context(patch.object(runtime,'_today',lambda:native.AS_OF+timedelta(days=1)))
            return value
        with patch.object(runtime,'_readback',readback),patch.object(runtime,'run_query',wraps=runtime.run_query) as core:
            self.error(await self.post(),409,'DATE_BOUNDARY_CHANGED')
        self.assertEqual(self.made,[])
        self.assertEqual(core.call_count,0)
        self.assertNotIn('embedding.constructor',self.fixture.events)
        self.assertNotIn('llm.constructor',self.fixture.events)

    async def test_midnight_inside_factory_denies_public_inference(self):
        original = self.app.state.runtime_factory
        def factory(*args):
            value = original(*args)
            self.stack.enter_context(patch.object(runtime,'_today',lambda:native.AS_OF+timedelta(days=1)))
            return value
        self.app.state.runtime_factory = factory
        with patch.object(runtime,'run_query',wraps=runtime.run_query) as core:
            self.error(await self.post(),409,'DATE_BOUNDARY_CHANGED')
        self.assertEqual(core.call_count,0)
        self.assertTrue(self.reader.closed)

    async def test_reader_source_backend_index_relations_changed_by_encoder_rejected(self):
        original = contract.encode_v1
        states = copy.deepcopy((self.reader.nodes,self.reader.metadata,self.reader.vector_indexes,self.reader.edges))
        for mutation in (lambda:self.reader.nodes['VietRoadTraffic.LegalUnit','unit-1']['properties'].update(text='changed'),
            lambda:self.reader.metadata.update(databaseID='foreign'),
            lambda:self.reader.vector_indexes[0].update(state='POPULATING'),lambda:self.reader.edges.clear()):
            def encode(payload):
                raw = original(payload)
                mutation()
                return raw
            with self.subTest(mutation=mutation.__code__.co_firstlineno),patch.object(contract,'encode_v1',encode):
                self.error(await self.post(),502,'SOURCE_VALIDATION_FAILED')
            self.reader.nodes,self.reader.metadata,self.reader.vector_indexes,self.reader.edges = copy.deepcopy(states)
            self.reader.closed = False

    async def test_selected_release_changed_during_cleanup_rejected(self):
        original = runtime.RequestRuntime.close
        async def close(instance):
            self.app.state.serving_release = replace(self.release,release_id='foreign')
            await asyncio.sleep(.01)
            await original(instance)
        with patch.object(runtime.RequestRuntime,'close',close):
            self.error(await self.post(),409,'RELEASE_MISMATCH')
        self.assertTrue(self.reader.closed)

    async def test_publication_changed_during_cleanup_rejected(self):
        original = runtime.RequestRuntime.close
        async def close(instance):
            (self.fixture.root/'webapp-publication.json').write_bytes(b'{}')
            await asyncio.sleep(.01)
            await original(instance)
        with patch.object(runtime.RequestRuntime,'close',close):
            self.error(await self.post(),502,'SOURCE_VALIDATION_FAILED')
        self.assertTrue(self.reader.closed)

    async def test_pending_body_send_crosses_midnight_never_completes_success(self):
        async def send(message):
            if message['type'] == 'http.response.body':
                self.stack.enter_context(patch.object(runtime,'_today',lambda:native.AS_OF+timedelta(days=1)))
                await asyncio.sleep(.2)
        messages = await self.raw_asgi(send)
        self.assertEqual(messages[0]['status'],200)
        self.assertFalse(any(m['type']=='http.response.body' for m in messages))

    async def test_authority_changes_after_headers_prevent_complete_body(self):
        async def send(message):
            if message['type'] == 'http.response.start':
                (self.fixture.root/'webapp-publication.json').write_bytes(b'{}')
        messages = await self.raw_asgi(send)
        self.assertEqual(messages[0]['status'],200)
        self.assertFalse(any(m['type']=='http.response.body' for m in messages))

    async def test_pending_body_send_publication_change_never_completes(self):
        async def send(message):
            if message['type'] == 'http.response.body':
                (self.fixture.root/'webapp-publication.json').write_bytes(b'{}')
                await asyncio.sleep(.2)
        messages = await self.raw_asgi(send)
        self.assertEqual(messages[0]['status'],200)
        self.assertFalse(any(m['type']=='http.response.body' for m in messages))

    async def test_actual_asgi_disconnect_holds_worker_clients_and_slot(self):
        entered,finish = threading.Event(),threading.Event()
        disconnect = asyncio.Event()
        with self.blocked_core(entered,finish):
            task = asyncio.create_task(self.raw_asgi(disconnect=disconnect))
            try:
                while not entered.is_set() and not task.done():
                    await asyncio.sleep(.001)
                self.assertTrue(entered.is_set())
                disconnect.set()
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(task,1)
                self.assertTrue(self.supervisor.busy and self.supervisor.draining)
                self.assertFalse(self.reader.closed)
            finally:
                finish.set()
                await self.supervisor.close()
        self.assertTrue(self.reader.closed)

    async def test_http_cleanup_failure_blocks_later_admission(self):
        original = self.reader.close
        def close():
            original()
            raise RuntimeError('synthetic-private-cleanup-error')
        with patch.object(self.reader,'close',close):
            self.error(await self.post(),500,'INTERNAL_ERROR')
        self.assertTrue(self.supervisor.closed)
        self.error(await self.post(),503,'NOT_READY')

    async def test_pending_body_send_deadline_never_completes(self):
        async def send(message):
            if message['type'] == 'http.response.body':
                await asyncio.sleep(2)
        with patch.object(runtime,'REQUEST_SECONDS',1):
            messages = await self.raw_asgi(send)
        self.assertEqual(messages[0]['status'],200)
        self.assertFalse(any(m['type']=='http.response.body' for m in messages))

    async def test_post_start_send_exception_has_no_complete_or_error_body(self):
        async def send(message):
            if message['type'] == 'http.response.body':
                raise OSError('synthetic-private-send-error')
        messages = await self.raw_asgi(send)
        self.assertEqual(messages[0]['status'],200)
        self.assertFalse(any(m['type']=='http.response.body' for m in messages))
