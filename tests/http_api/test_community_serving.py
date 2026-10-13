"""Offline Community authority tests; live network evidence remains independent."""
import copy
import json
import io
from types import SimpleNamespace
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from kag.http_api import artifacts, community
from test_sample_serving import SampleFixture
from test_artifacts import sha, raw_json

class CommunityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.fx=SampleFixture(Path(self.temp.name))
        self.proof={k:v for k,v in self.fx.proof.items() if k not in ('reader_username','reader_privileges_verified')}
        self.proof.update(schema='h1-community-sample-1.0',broker_url='http://openspg-server:8899',
            broker_code_sha256='b'*64,isolation={'neo4j_ip':'172.20.0.2','server_ip':'172.20.0.3',
                'api_has_database_credentials':False,'api_has_docker_socket':False,
                'api_container_id':'a'*64,'server_container_id':'c'*64,'neo4j_container_id':'d'*64,
                'read_network_id':'e'*64,'database_network_id':'f'*64})
        self.seal()
    def seal(self):
        raw=raw_json(self.proof);(self.fx.root/'sample-serving.json').write_bytes(raw);self.pin=sha(raw)
    def load(self):
        return artifacts.load_sample_proof(self.fx.release,self.pin,None)
    def test_separate_authority_never_claims_rbac(self):
        proof=self.load();self.assertNotIn('reader_privileges_verified',proof)
    def test_production_denied(self):
        from dataclasses import replace
        self.fx.release=replace(self.fx.release,release_kind='PRODUCTION')
        with self.assertRaises(artifacts.ArtifactFailure):self.load()
    def test_binding_and_missing_control_denied(self):
        for field,value in [('namespace','Other'),('database_id','other'),('graph_fingerprint','0'*64),
                ('release_descriptor_sha256','0'*64),('source_snapshot_id','wrong')]:
            with self.subTest(field=field):
                saved=copy.deepcopy(self.proof);self.proof[field]=value;self.seal()
                with self.assertRaises(artifacts.ArtifactFailure):self.load()
                self.proof=saved;self.seal()
        del self.proof['isolation'];self.seal()
        with self.assertRaises(artifacts.ArtifactFailure):self.load()
    def test_database_credentials_or_socket_denied(self):
        for field in ('api_has_database_credentials','api_has_docker_socket'):
            self.proof['isolation'][field]=True;self.seal()
            with self.assertRaises(artifacts.ArtifactFailure):self.load()
            self.proof['isolation'][field]=False
    def test_catalog_and_proof_pin_drift_denied(self):
        (self.fx.root/'sample-serving.json').write_bytes(b'{}')
        with self.assertRaises(artifacts.ArtifactFailure):self.load()
    def test_isolation_tcp_accessible_denied(self):
        with patch.object(community.socket,'gethostbyname',return_value='172.20.0.3'), patch.object(community.socket,'create_connection',return_value=object()):
            with self.assertRaises(ValueError):community.verify_isolation(self.proof)
    def test_isolation_tcp_denied_accepted(self):
        with patch.object(community.socket,'gethostbyname',return_value='172.20.0.3'), patch.object(community.socket,'create_connection',side_effect=OSError('denied')) as conn:
            community.verify_isolation(self.proof);self.assertEqual(conn.call_count,3)
    def test_stale_broker_ip_denied(self):
        with patch.object(community.socket,'gethostbyname',return_value='172.20.0.9'):
            with self.assertRaises(ValueError):community.verify_isolation(self.proof)
    def test_broker_response_identity_hash_readonly_and_ip_drift_denied(self):
        client=community.BrokerRetrievalClient(self.fx.release,self.load(),'t'*43,timeout=1)
        readonly={'database':client.database,'database_id':self.fx.release.descriptor['database_id'],
            'server_id':self.fx.release.descriptor['server_id'],'access':'read-only','setting':client.database}
        response={'rows':[],'readonly':readonly,'broker_code_sha256':'b'*64,'backend_ip':'172.20.0.2'}
        def read(value):
            client._opener=SimpleNamespace(open=lambda *a,**kw:io.BytesIO(raw_json(value)))
            return client._query('indexes')
        self.assertEqual(read(response),[])
        mutations=[('backend_ip','172.20.0.9'),('broker_code_sha256','0'*64),('readonly',dict(readonly,access='read-write'))]
        for key,value in mutations:
            with self.subTest(key=key):
                with self.assertRaises(artifacts.ArtifactFailure):read(dict(response,**{key:value}))

    def test_api_vector_uses_real_community_broker_full_graph_and_denies_readonly_drift(self):
        import asyncio
        import httpx
        from kag.http_api import read_broker, runtime
        from kag.http_api.app import ApiSettings, create_app
        from kag.vector_contract import TARGETS
        from urllib.error import HTTPError
        from test_sample_serving import SECRETS
        from test_artifacts import IDENTITY

        fx = self.fx
        fx.database,fx.endpoint = 'vietroadtraffic','http://openspg-neo4j:7474'
        fx.metadata['name'] = fx.database
        for value in (fx.binding,fx.catalog,fx.graph,fx.backend,fx.authority,fx.descriptor):
            value['database'] = fx.database
        for value in (fx.backend,fx.authority): value['reader_endpoint'] = fx.endpoint
        fx.seal(publication=False)
        fx.release = artifacts.load_release(fx.root,'synthetic-release')
        self.proof.update(database=fx.database,release_descriptor_sha256=fx.release.descriptor_sha256,
                          broker_code_sha256=sha(Path(read_broker.__file__).read_bytes()))
        self.seal()

        class BackendReader:
            database,endpoint = fx.database,fx.endpoint
            access,drift = 'read-only',False
            def __init__(inner): inner.operations=[]
            def database_metadata(inner): return fx.database_metadata()
            def indexes(inner): return fx.indexes()
            def readonly_state(inner):
                return {'catalog':[{'name':fx.database,'access':inner.access,'currentStatus':'online'}],
                        'settings':[{'name':'server.databases.read_only','value':fx.database}]}
            def _query(inner,name,p):
                inner.operations.append(name)
                if name in ('database_metadata','databases'): return [fx.database_metadata()]
                if name=='indexes': return fx.indexes()
                if name in ('nodes','edges'):
                    rows=list(fx.nodes.values()) if name=='nodes' else fx.edges
                    return copy.deepcopy(sorted((r for r in rows if r['physical_id']>p['cursor']),
                                                key=lambda r:r['physical_id'])[:p['limit']])
                if name=='batch_nodes': return fx.read_nodes(p['keys'])
                if name=='batch_edges': return fx.read_edges(p['keys'])
                if name=='retrieval_expand':
                    return [{'from_labels':[fx.relation['from'][0]],'from_id':fx.relation['from'][1],
                             'predicate':fx.relation['predicate'],'to_labels':[fx.relation['to'][0]],
                             'to_id':fx.relation['to'][1]}]
                if name=='retrieval_vector':
                    kind=p['label'].rsplit('.',1)[1]
                    index=next(i for i in fx.vector_indexes if i['name']==p['index'])
                    prop=next(prop for prop,field in TARGETS[kind] if field==index['properties'][0])
                    rows=fx.vector_search(kind,prop,p['vector'],p['k'])
                    if inner.drift: inner.access='read-write'
                    return [{'id':r['id'],'score':r['score']} for r in rows]
                raise AssertionError('unexpected broker operation: '+name)

        backend=BackendReader()
        policy=read_broker.ReadBroker(backend,'t'*43,fx.metadata['databaseID'],fx.metadata['serverID'])
        class BrokerOpener:
            def open(inner,request,*,timeout):
                self.assertEqual(request.full_url,'http://openspg-server:8899/read')
                self.assertEqual(request.get_method(),'POST')
                try:
                    result=policy.read(json.loads(request.data),request.get_header('Authorization'))
                except read_broker.BrokerFailure as error:
                    raise HTTPError(request.full_url,error.status,'DENIED',None,
                                    io.BytesIO(b'{"error":"DENIED"}')) from None
                return io.BytesIO(raw_json(result))
        def resolve(host):
            if host=='openspg-server': return '172.20.0.3'
            if host=='openspg-neo4j': return '172.20.0.2'
            raise AssertionError('unexpected DNS target')
        def blocked(address,*,timeout):
            self.assertIn(address,(('172.20.0.2',7474),('172.20.0.2',7687),('172.20.0.3',8887)))
            raise ConnectionRefusedError('offline isolation fixture')

        app=create_app(ApiSettings(SECRETS),enable_sample_routes=True)
        app.state.serving_release=fx.release
        app.state.runtime_settings=runtime.RuntimeSettings(secrets=SECRETS,
            release_id='synthetic-release',source_snapshot_id='synthetic-source',
            sample_proof_sha256=self.pin,broker_url=self.proof['broker_url'],broker_token='t'*43)
        app.state.runtime_supervisor=runtime.RuntimeSupervisor()
        async def exercise():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://fixture.invalid') as client:
                headers={'authorization':'Bearer '+'i'*43,'x-kag-release-id':'synthetic-release'}
                ready=await client.get('/v1/health?mode=ready&capability=retrieve-vector',headers=headers)
                self.assertEqual(ready.status_code,200,ready.text)
                body={'evidence_id':fx.evidence_id,'schema_contract':IDENTITY,'top_k':1,'expand':True}
                result=await client.post('/v1/retrieve/vector',headers=headers,json=body)
                self.assertEqual(result.status_code,200,result.text)
                self.assertEqual(result.json()['items'][0]['entity_id'],'unit-1')
                self.assertEqual(result.json()['release_kind'],'SAMPLE')
                self.assertEqual(fx.searches,4)
                self.assertTrue({'nodes','edges','batch_nodes','batch_edges','retrieval_expand',
                                 'retrieval_vector'}<=set(backend.operations))
                self.assertFalse({'reader_identity','reader_privileges'}&set(backend.operations))
                backend.drift=True
                denied=await client.post('/v1/retrieve/vector',headers=headers,json=body)
                self.assertEqual(denied.status_code,503,denied.text)
                self.assertEqual(backend.access,'read-write')
        with patch.object(runtime,'initialize_runtime'), \
                patch.object(community,'build_opener',return_value=BrokerOpener()), \
                patch.object(community.socket,'gethostbyname',side_effect=resolve), \
                patch.object(community.socket,'create_connection',side_effect=blocked), \
                patch.object(runtime,'_new_embedding',side_effect=AssertionError('provider forbidden')) as embedding, \
                patch.object(runtime,'_new_llm',side_effect=AssertionError('chat forbidden')) as chat:
            asyncio.run(exercise())
        embedding.assert_not_called();chat.assert_not_called()

if __name__=='__main__':unittest.main()
