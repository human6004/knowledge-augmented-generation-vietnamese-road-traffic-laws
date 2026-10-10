"""Offline packaging tests; execute only in canonical CPython 3.10.16/Linux amd64."""
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

import httpx

from kag.http_api import server


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='step8-server-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.query = self.root/'query.token'
        self.inspect = self.root/'inspect.token'
        self.query.write_text('q'*64, encoding='ascii')
        self.inspect.write_text('i'*64, encoding='ascii')
        self.env = {'KAG_HTTP_QUERY_SECRET_FILE':str(self.query),
                    'KAG_HTTP_INSPECT_SECRET_FILE':str(self.inspect)}
        self.environment = patch.dict(os.environ, self.env, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_factory_registers_existing_h1_routes_without_serving_authority(self):
        app = server.create_app()
        self.assertTrue({'/v1/health','/v1/graph/release','/v1/query',
                         '/v1/query/stream','/v1/retrieve'} <= {r.path for r in app.routes})
        self.assertIsNone(app.state.serving_release)
        self.assertIsNone(app.state.runtime_settings)
        self.assertIsNone(app.openapi_url)

    def test_both_service_scopes_are_required(self):
        for key in self.env:
            with self.subTest(key=key), patch.dict(os.environ, self.env, clear=True):
                del os.environ[key]
                with self.assertRaises(server.ConfigurationError):
                    server.create_app()

    def test_invalid_missing_or_identical_tokens_fail_closed(self):
        for value in ('short', 'q'*64, 'i'*515):
            with self.subTest(value_length=len(value)):
                self.inspect.write_text(value, encoding='ascii')
                with self.assertRaises(server.ConfigurationError):
                    server.create_app()
        self.inspect.unlink()
        with self.assertRaises(server.ConfigurationError):
            server.create_app()

    def test_secret_failure_message_does_not_expose_payload_or_path(self):
        secret = 'unprintable-secret-value'
        self.inspect.write_text(secret, encoding='ascii')
        with self.assertRaises(server.ConfigurationError) as caught:
            server.create_app()
        self.assertNotIn(secret, str(caught.exception))
        self.assertNotIn(str(self.inspect), str(caught.exception))

    def test_env_cannot_enable_writes_providers_or_operational_proof(self):
        for key,value in [('KAG_OPERATIONAL_PROOF','ALLOW'),('KAG_PRODUCTION_WRITE','ALLOW'),
                          ('KAG_PROVIDER_EGRESS','ALLOW'),('KAG_DEBUG_DUMP_CONFIG','1'),
                          ('KAG_PROJECT_ID','1'),('KAG_PROJECT_HOST_ADDR','http://localhost:8887')]:
            with self.subTest(key=key), patch.dict(os.environ, {key:value}):
                with self.assertRaises(server.ConfigurationError):
                    server.create_app()

    def test_release_id_without_root_is_rejected(self):
        with patch.dict(os.environ, {'KAG_HTTP_RELEASE_ID':'not-a-test-release'}):
            with self.assertRaises(server.ConfigurationError):
                server.create_app()

    def test_unsealed_release_is_rejected_without_network(self):
        with patch.dict(os.environ, {'KAG_HTTP_RELEASE_ID':'release-1',
                                    'KAG_HTTP_RELEASE_ROOT':str(self.root)}):
            with self.assertRaises(server.ConfigurationError):
                server.create_app()

    def test_sealed_fixture_is_loaded_locally_but_proof_still_denies(self):
        from test_artifacts import EvidenceFixture
        from kag.http_api import artifacts, runtime
        EvidenceFixture(self.root)
        with patch.dict(os.environ, {'KAG_HTTP_RELEASE_ID':'synthetic-release',
                                    'KAG_HTTP_RELEASE_ROOT':str(self.root)}):
            app = server.create_app()
        self.assertEqual(app.state.serving_release.release_id, 'synthetic-release')
        self.assertEqual(app.state.runtime_settings.source_snapshot_id,
                         app.state.serving_release.descriptor['source_snapshot_id'])
        with self.assertRaises(artifacts.ArtifactFailure) as caught:
            runtime._require_operational_proof(app.state.runtime_settings, app.state.serving_release)
        self.assertIs(caught.exception.state, artifacts.VerificationState.UNVERIFIED)

    def test_admin_reader_credentials_are_not_accepted(self):
        password = self.root/'reader.password'
        password.write_text('r'*64, encoding='ascii')
        for user in ('root','neo4j','admin'):
            with self.subTest(user=user), patch.dict(os.environ, {
                    'KAG_HTTP_READER_USERNAME':user,'KAG_HTTP_READER_PASSWORD_FILE':str(password)}):
                with self.assertRaises(server.ConfigurationError):
                    server.create_app()

    def test_transport_rejects_multiple_workers_and_malformed_ports(self):
        for key,value in [('KAG_HTTP_WORKERS','2'),('KAG_HTTP_PORT','0'),
                          ('KAG_HTTP_PORT','65536'),('KAG_HTTP_PORT','8000x'),
                          ('KAG_HTTP_HOST','example.invalid')]:
            with self.subTest(key=key,value=value), patch.dict(os.environ, {key:value}):
                with self.assertRaises(server.ConfigurationError):
                    server.server_options()

    def test_transport_defaults_and_portable_port_override(self):
        self.assertEqual(server.server_options(), ('0.0.0.0',8000))
        with patch.dict(os.environ, {'KAG_HTTP_HOST':'127.0.0.1','KAG_HTTP_PORT':'38000'}):
            self.assertEqual(server.server_options(), ('127.0.0.1',38000))

    def test_empty_optional_compose_values_do_not_grant_runtime_authority(self):
        with patch.dict(os.environ, {'KAG_HTTP_RELEASE_ROOT':'','KAG_HTTP_RELEASE_ID':'',
                'KAG_HTTP_READER_USERNAME':'','KAG_HTTP_READER_PASSWORD_FILE':'',
                'KAG_HTTP_EMBEDDING_KEY_FILE':'','KAG_HTTP_CHAT_KEY_FILE':''}):
            app = server.create_app()
        self.assertIsNone(app.state.serving_release)
        self.assertIsNone(app.state.runtime_settings)


class PackagedASGITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='step8-asgi-')
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name,token in [('query','q'),('inspect','i')]:
            (root/(name+'.token')).write_text(token*64, encoding='ascii')
        environment = patch.dict(os.environ, {
            'KAG_HTTP_QUERY_SECRET_FILE':str(root/'query.token'),
            'KAG_HTTP_INSPECT_SECRET_FILE':str(root/'inspect.token')}, clear=True)
        environment.start(); self.addCleanup(environment.stop)
        from kag.http_api import runtime
        self.external_io = []
        for module,name in [(socket.socket,'connect'),(socket.socket,'connect_ex'),
                            (runtime,'_new_reader'),(runtime,'_new_embedding'),(runtime,'_new_llm')]:
            blocker = patch.object(module,name,side_effect=AssertionError('External I/O forbidden'))
            self.external_io.append(blocker.start()); self.addCleanup(blocker.stop)
        self.app = server.create_app()
        self.lifespan = self.app.router.lifespan_context(self.app)
        await self.lifespan.__aenter__()
        self.addAsyncCleanup(self.lifespan.__aexit__,None,None,None)
        self.assertFalse(self.app.state.runtime_supervisor.closed)
        for blocker in self.external_io:
            blocker.assert_not_called()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app,
            client=('192.0.2.10',45000)),base_url='http://offline.test')
        self.addAsyncCleanup(self.client.aclose)

    async def asyncTearDown(self):
        for blocker in self.external_io:
            blocker.assert_not_called()

    async def test_remote_liveness_requires_bearer_even_with_forwarded_loopback(self):
        result = await self.client.get('/v1/health', headers={'x-forwarded-for':'127.0.0.1'})
        self.assertEqual(result.status_code,401)
        self.assertEqual(result.json()['error']['code'],'AUTH_REQUIRED')

    async def test_authenticated_liveness_does_not_claim_ready(self):
        result = await self.client.get('/v1/health',headers={'authorization':'Bearer '+'i'*64})
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json()['status'],'alive')

    async def test_capability_readiness_remains_503_without_provider_probe(self):
        for capability,token in [('retrieve','i'),('query-v1','q')]:
            result = await self.client.get('/v1/health',params={'mode':'ready','capability':capability},
                headers={'authorization':'Bearer '+token*64})
            self.assertEqual(result.status_code,503)
            self.assertEqual(result.json()['error']['code'],'NOT_READY')
            self.assertEqual(result.json()['production_write'],'blocked')
            self.assertEqual(result.json()['provider_transport'],'not_probed')

    async def test_retrieve_admission_keeps_existing_auth_and_scope_policy(self):
        for headers,status in [({},401),({'authorization':'Bearer '+'q'*64},403)]:
            result = await self.client.post('/v1/retrieve',headers=headers,content=b'{')
            self.assertEqual(result.status_code,status)

    async def test_valid_retrieve_is_unavailable_without_release(self):
        result = await self.client.post('/v1/retrieve',headers={'authorization':'Bearer '+'i'*64},
            json={'message':'q','schema_contract':{'namespace':'VietRoadTraffic',
                'schema_sha256':'a'*64,'contract_sha256':'b'*64}})
        self.assertEqual(result.status_code,503)
        self.assertEqual(result.json()['error']['code'],'RELEASE_UNAVAILABLE')

    async def test_query_and_sse_preserve_fail_closed_response(self):
        payload={'user_id':'00000000-0000-4000-8000-000000000001','message':'q',
            'schema_contract':{'namespace':'VietRoadTraffic','schema_sha256':'a'*64,'contract_sha256':'b'*64}}
        for path in ('/v1/query','/v1/query/stream'):
            result = await self.client.post(path,headers={'authorization':'Bearer '+'q'*64},json=payload)
            self.assertEqual(result.status_code,503)
            self.assertEqual(result.json()['error']['code'],'RELEASE_UNAVAILABLE')
            self.assertEqual(result.headers['cache-control'],'no-store')


if __name__ == '__main__':
    unittest.main()
