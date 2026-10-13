"""Offline shell tests; POST routes exist only in this test fixture."""
import asyncio
import contextlib
import io
import importlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import UUID

import httpx
from fastapi import HTTPException, Request

from kag.http_api.contract import ApiFailure, QueryV1Request

try:
    shell = importlib.import_module('kag.http_api.app')
    security = importlib.import_module('kag.http_api.security')
except ModuleNotFoundError as exc:
    if exc.name not in ('kag.http_api.app', 'kag.http_api.security'):
        raise
    shell = security = None

QUERY_TOKEN = 'Q' * 43  # Synthetic test credential only.
OLD_TOKEN = 'P' * 43
INSPECT_TOKEN = 'I' * 43
USER = '00000000-0000-4000-8000-000000000001'
OTHER_USER = '00000000-0000-4000-8000-000000000002'
LIMIT = 65536


def payload(**changes):
    return {'user_id': USER, 'message': ' Câu hỏi e\u0301 😀 ', 'context_id': '',
            'schema_contract': {'namespace': 'VietRoadTraffic',
                                'schema_sha256': 'a' * 64, 'contract_sha256': 'b' * 64}, **changes}


def raw(**changes):
    return json.dumps(payload(**changes), ensure_ascii=False).encode('utf-8')


class SecurityPolicyTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(security, 'Step 2 authentication/admission behavior is missing')
        self.secrets = security.ServiceSecrets((QUERY_TOKEN, OLD_TOKEN), (INSPECT_TOKEN,))

    def failure(self, code, call):
        with self.assertRaises(ApiFailure) as caught:
            call()
        self.assertEqual(caught.exception.code, code)

    def test_missing_bearer(self):
        self.failure('AUTH_REQUIRED', lambda: security.authenticate(None, self.secrets))

    def test_invalid_bearer_forms(self):
        for header in ('', 'Basic '+QUERY_TOKEN, 'Bearer', 'Bearer ', 'Bearer  '+QUERY_TOKEN,
                       'Bearer '+QUERY_TOKEN+' ', 'Bearer '+QUERY_TOKEN+'\n',
                       'Bearer wrong', 'Bearer 😀', 'Bearer '+QUERY_TOKEN+', '+OLD_TOKEN):
            with self.subTest(header_index=len(header)):
                self.failure('AUTH_INVALID', lambda: security.authenticate(header, self.secrets))

    def test_query_principal_and_delegation(self):
        principal = security.authenticate('Bearer '+QUERY_TOKEN, self.secrets)
        self.assertEqual(principal.service_id, 'webapp-query')
        self.assertEqual(principal.scopes, frozenset({'query'}))
        self.assertTrue(principal.can_delegate_user)
        security.authorize(principal, 'query', UUID(USER))

    def test_case_insensitive_bearer_scheme(self):
        self.assertEqual(security.authenticate('bEaReR '+QUERY_TOKEN, self.secrets).service_id,
                         'webapp-query')

    def test_previous_secret_rotation(self):
        self.assertEqual(security.authenticate('Bearer '+OLD_TOKEN, self.secrets).service_id,
                         'webapp-query')

    def test_inspect_principal_cannot_query_or_delegate(self):
        principal = security.authenticate('Bearer '+INSPECT_TOKEN, self.secrets)
        self.assertEqual(principal.scopes, frozenset({'inspect'}))
        security.authorize(principal, 'inspect', None)
        self.failure('SCOPE_DENIED', lambda: security.authorize(principal, 'query', None))
        self.failure('DELEGATION_DENIED', lambda: security.authorize(principal, 'inspect', UUID(USER)))

    def test_non_delegating_query_principal_rejected(self):
        principal = security.ServicePrincipal('fixture', frozenset({'query'}), False)
        self.failure('DELEGATION_DENIED', lambda: security.authorize(principal, 'query', UUID(USER)))

    def test_write_and_admin_scopes_denied(self):
        principal = security.authenticate('Bearer '+QUERY_TOKEN, self.secrets)
        for scope in ('write', 'admin', 'admin-control', 'inspect'):
            self.failure('SCOPE_DENIED', lambda: security.authorize(principal, scope, None))

    def test_user_id_string_is_not_verified_delegation(self):
        principal = security.authenticate('Bearer '+QUERY_TOKEN, self.secrets)
        self.failure('INVALID_REQUEST', lambda: security.authorize(principal, 'query', USER))

    def test_deny_by_default(self):
        self.failure('AUTH_INVALID', lambda: security.authenticate('Bearer '+QUERY_TOKEN,
                                                                   security.ServiceSecrets()))

    def test_constant_time_comparison_checks_all_keys(self):
        with patch.object(security.hmac, 'compare_digest', wraps=security.hmac.compare_digest) as spy:
            security.authenticate('Bearer '+QUERY_TOKEN, self.secrets)
        self.assertEqual(spy.call_count, 3)

    def test_secret_policy_rejects_short_duplicate_or_excess_rotation(self):
        for query, inspect in ((('short',), ()), ((QUERY_TOKEN,), (QUERY_TOKEN,)),
                               ((QUERY_TOKEN, OLD_TOKEN, INSPECT_TOKEN), ()),
                               (['Q' * 43], ()), (('😀' * 32,), ())):
            with self.subTest(case_type=type(query).__name__):
                with self.assertRaises(ApiFailure) as caught:
                    security.ServiceSecrets(query, inspect)
                self.assertEqual(caught.exception.code, 'NOT_READY')

    def test_secrets_never_appear_in_repr(self):
        self.assertNotIn(QUERY_TOKEN, repr(self.secrets))
        self.assertNotIn(OLD_TOKEN, repr(shell.ApiSettings(self.secrets)))

    def test_secret_files_and_absent_environment(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = shell.ApiSettings.from_env()
            self.failure('AUTH_INVALID', lambda: security.authenticate('Bearer '+QUERY_TOKEN,
                                                                       settings.secrets))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'query.key'
            path.write_text(QUERY_TOKEN+'\n', encoding='ascii')
            with patch.dict(os.environ, {'KAG_HTTP_QUERY_SECRET_FILE': str(path)}, clear=True):
                settings = shell.ApiSettings.from_env()
                self.assertEqual(security.authenticate('Bearer '+QUERY_TOKEN,
                                                       settings.secrets).service_id, 'webapp-query')

    def test_bad_secret_file_is_sanitized(self):
        with patch.dict(os.environ, {'KAG_HTTP_QUERY_SECRET_FILE': '/missing/private/provider-secret'}, clear=True):
            with self.assertRaises(ApiFailure) as caught:
                shell.ApiSettings.from_env()
        self.assertEqual(caught.exception.code, 'NOT_READY')
        self.assertNotIn('/missing', str(caught.exception))

    def test_secret_file_cannot_be_partially_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'query.key'
            path.write_bytes(b'Q'*512+b'\nignored-secret-tail')
            with patch.dict(os.environ, {'KAG_HTTP_QUERY_SECRET_FILE': str(path)}, clear=True):
                with self.assertRaises(ApiFailure) as caught:
                    shell.ApiSettings.from_env()
            self.assertEqual(caught.exception.code, 'NOT_READY')

    def test_invalid_settings_and_principal_types(self):
        self.failure('NOT_READY', lambda: shell.ApiSettings('secret'))
        self.failure('NOT_READY', lambda: shell.create_app(settings={}))
        for scopes, delegate in (({'query'}, True), (frozenset({'write'}), True),
                                 (frozenset({'query'}), 1)):
            self.failure('NOT_READY', lambda: security.ServicePrincipal('fixture', scopes, delegate))

    def test_environment_rotation_files(self):
        with tempfile.TemporaryDirectory() as directory:
            query, previous, inspect = [Path(directory)/n for n in ('query','previous','inspect')]
            for path, token in ((query, QUERY_TOKEN), (previous, OLD_TOKEN), (inspect, INSPECT_TOKEN)):
                path.write_bytes(token.encode('ascii')+b'\r\n')
            with patch.dict(os.environ, {'KAG_HTTP_QUERY_SECRET_FILE': str(query),
                'KAG_HTTP_QUERY_PREVIOUS_SECRET_FILE': str(previous),
                'KAG_HTTP_INSPECT_SECRET_FILE': str(inspect)}, clear=True):
                settings = shell.ApiSettings.from_env()
            self.assertEqual(security.authenticate('Bearer '+OLD_TOKEN, settings.secrets).service_id, 'webapp-query')
            self.assertEqual(security.authenticate('Bearer '+INSPECT_TOKEN, settings.secrets).service_id, 'inspect')


class AdmissionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertIsNotNone(shell, 'Step 2 HTTP/auth admission shell is missing')
        self.factory = Mock(side_effect=AssertionError('runtime factory must not initialize'))
        self.app = shell.create_app(shell.ApiSettings(security.ServiceSecrets(
            (QUERY_TOKEN,), (INSPECT_TOKEN,))), runtime_factory=self.factory)

        @self.app.post('/_admission', include_in_schema=False)
        async def admitted(request: Request):
            dto = await security.admit_request(request, 'query', QueryV1Request)
            return {'message': dto.message, 'user_id': str(request.state.delegated_user_id),
                    'service_id': request.state.service_principal.service_id}

        @self.app.get('/_error', include_in_schema=False)
        async def failed():
            raise RuntimeError('provider endpoint private-secret '+QUERY_TOKEN)

        @self.app.get('/_http_error', include_in_schema=False)
        async def http_failed():
            raise HTTPException(status_code=400, detail='provider private-secret '+QUERY_TOKEN)

        self.transport = httpx.ASGITransport(app=self.app, client=('203.0.113.1', 1234),
                                             raise_app_exceptions=False)
        self.client = httpx.AsyncClient(transport=self.transport, base_url='http://fixture')

    async def asyncTearDown(self):
        await self.client.aclose()
        self.factory.assert_not_called()

    async def post(self, data=None, headers=None):
        return await self.client.post('/_admission', content=raw() if data is None else data,
                                      headers={'Authorization': 'Bearer '+QUERY_TOKEN,
                                               'Content-Type': 'application/json', **(headers or {})})

    def error(self, response, status, code):
        self.assertEqual(response.status_code, status, response.text)
        body = response.json()
        self.assertEqual(body['error']['code'], code)
        self.assertFalse(body['error']['retryable'])
        self.assertIsNone(body['native_state'])
        self.assertEqual(str(UUID(body['request_id'])), response.headers['x-request-id'])
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertLessEqual(len(response.content), 4096)
        for forbidden in (QUERY_TOKEN, INSPECT_TOKEN, 'private-secret', 'Traceback'):
            self.assertNotIn(forbidden, response.text)

    async def test_no_bearer_401_before_parser(self):
        with patch.object(QueryV1Request, 'from_json', side_effect=AssertionError('parser bypass')) as parser:
            response = await self.client.post('/_admission', content=raw(), headers={'Content-Type': 'application/json'})
        self.error(response, 401, 'AUTH_REQUIRED')
        self.assertEqual(response.headers['www-authenticate'], 'Bearer')
        parser.assert_not_called()

    async def test_invalid_bearer_401(self):
        self.error(await self.post(headers={'Authorization': 'Bearer browser-jwt'}), 401, 'AUTH_INVALID')

    async def test_malformed_bearer_401(self):
        self.error(await self.post(headers={'Authorization': 'Basic '+QUERY_TOKEN}), 401, 'AUTH_INVALID')

    async def test_duplicate_authorization_rejected(self):
        response = await self.client.post('/_admission', content=raw(), headers=[
            ('Content-Type', 'application/json'), ('Authorization', 'Bearer '+QUERY_TOKEN),
            ('Authorization', 'Bearer '+INSPECT_TOKEN)])
        self.error(response, 401, 'AUTH_INVALID')

    async def test_scope_denied_before_parser(self):
        with patch.object(QueryV1Request, 'from_json', side_effect=AssertionError('parser bypass')) as parser:
            response = await self.post(headers={'Authorization': 'Bearer '+INSPECT_TOKEN,
                                                'X-Role': 'admin', 'X-Scope': 'query'})
        self.error(response, 403, 'SCOPE_DENIED')
        parser.assert_not_called()

    async def test_delegation_denied(self):
        principal = security.ServicePrincipal('fixture', frozenset({'query'}), False)
        with patch.object(security, 'authenticate', return_value=principal):
            response = await self.post()
        self.error(response, 403, 'DELEGATION_DENIED')

    async def test_body_user_id_not_authentication(self):
        response = await self.client.post('/_admission', content=raw(), headers={'Content-Type': 'application/json',
            'X-User-ID': USER, 'X-Service-ID': 'webapp-query'})
        self.error(response, 401, 'AUTH_REQUIRED')

    async def test_forged_identity_header_rejected(self):
        self.error(await self.post(headers={'X-User-ID': OTHER_USER}), 422, 'INVALID_REQUEST')

    async def test_forged_role_field_rejected(self):
        self.error(await self.post(raw(role='admin')), 422, 'INVALID_REQUEST')

    async def test_authenticated_delegated_request_preserves_text(self):
        response = await self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'message': payload()['message'], 'user_id': USER,
                                           'service_id': 'webapp-query'})

    async def test_canonical_parser_is_single_path(self):
        with patch.object(QueryV1Request, 'from_json', wraps=QueryV1Request.from_json) as from_json, \
             patch.object(QueryV1Request, 'from_dict', wraps=QueryV1Request.from_dict) as from_dict, \
             patch.object(Request, 'json', side_effect=AssertionError('permissive decoder forbidden')):
            response = await self.post()
        self.assertEqual(response.status_code, 200)
        from_json.assert_called_once()
        self.assertIs(type(from_json.call_args.args[0]), bytes)
        from_dict.assert_called_once()

    async def test_content_length_oversized_before_parser(self):
        with patch.object(QueryV1Request, 'from_json', side_effect=AssertionError('oversized JSON parsed')) as parser:
            response = await self.post(b'{', {'Content-Length': str(LIMIT+1)})
        self.error(response, 413, 'REQUEST_TOO_LARGE')
        parser.assert_not_called()

    async def test_exact_64k_body_passes(self):
        body = raw()
        self.assertEqual((await self.post(body+b' '*(LIMIT-len(body)))).status_code, 200)

    async def test_one_byte_above_limit(self):
        body = raw()
        self.error(await self.post(body+b' '*(LIMIT+1-len(body))), 413, 'REQUEST_TOO_LARGE')

    async def test_chunked_oversized_body_before_parser(self):
        async def chunks():
            yield b' ' * (LIMIT//2)
            yield b' ' * (LIMIT//2)
            yield b'!'
        with patch.object(QueryV1Request, 'from_json', side_effect=AssertionError('oversized JSON parsed')) as parser:
            response = await self.post(chunks())
        self.error(response, 413, 'REQUEST_TOO_LARGE')
        parser.assert_not_called()

    async def test_chunked_exact_limit(self):
        body = raw()
        async def chunks():
            yield body
            yield b' ' * (LIMIT-len(body))
        self.assertEqual((await self.post(chunks())).status_code, 200)

    async def test_false_short_content_length_cannot_bypass_limit(self):
        self.error(await self.post(b' '*(LIMIT+1), {'Content-Length': '1'}), 413, 'REQUEST_TOO_LARGE')

    async def test_content_length_mismatch_rejected(self):
        self.error(await self.post(raw(), {'Content-Length': '1'}), 422, 'INVALID_REQUEST')

    async def test_malformed_content_length(self):
        for value in ('-1', '1.0', '+3', 'abc'):
            self.error(await self.post(headers={'Content-Length': value}), 422, 'INVALID_REQUEST')

    async def test_json_utf8_content_type(self):
        self.assertEqual((await self.post(headers={'Content-Type': 'application/json; charset=utf-8'})).status_code, 200)

    async def test_unsupported_media_types(self):
        for value in ('text/plain', 'application/xml', 'application/problem+json',
                      'application/json; charset=utf-16', 'application/json; unknown=x'):
            self.error(await self.post(headers={'Content-Type': value}), 415, 'UNSUPPORTED_MEDIA_TYPE')

    async def test_missing_content_type(self):
        response = await self.client.post('/_admission', content=raw(), headers={'Authorization': 'Bearer '+QUERY_TOKEN})
        self.error(response, 415, 'UNSUPPORTED_MEDIA_TYPE')

    async def test_unsupported_encoding(self):
        for value in ('gzip', 'br', 'deflate', 'identity, gzip'):
            self.error(await self.post(headers={'Content-Encoding': value}), 415, 'UNSUPPORTED_MEDIA_TYPE')

    async def test_identity_encoding_allowed(self):
        self.assertEqual((await self.post(headers={'Content-Encoding': 'identity'})).status_code, 200)

    async def test_duplicate_content_type(self):
        response = await self.client.post('/_admission', content=raw(), headers=[
            ('Authorization', 'Bearer '+QUERY_TOKEN), ('Content-Type', 'application/json'),
            ('Content-Type', 'application/json')])
        self.error(response, 415, 'UNSUPPORTED_MEDIA_TYPE')

    async def test_duplicate_json_keys(self):
        self.error(await self.post(raw()[:-1]+b',"message":"forged"}'), 400, 'INVALID_JSON')

    async def test_nested_duplicate_json_keys(self):
        self.error(await self.post(raw().replace(b'"namespace":', b'"namespace":"forged","namespace":')),
                   400, 'INVALID_JSON')

    async def test_nan_and_infinities(self):
        for token in (b'NaN', b'Infinity', b'-Infinity', b'1e999'):
            self.error(await self.post(raw()[:-1]+b',"extra":'+token+b'}'), 400, 'INVALID_JSON')

    async def test_bom_invalid_utf8_surrogate(self):
        for body in (b'\xef\xbb\xbf'+raw(), b'\xff', raw()[:-1]+b',"extra":"\\ud800"}'):
            self.error(await self.post(body), 400, 'INVALID_JSON')

    async def test_malformed_json(self):
        for body in (b'', b'{', b'{} trailing', b'{"x":', b'['*1500):
            self.error(await self.post(body), 400, 'INVALID_JSON')

    async def test_unknown_keys(self):
        self.error(await self.post(raw(provider='private-secret')), 422, 'INVALID_REQUEST')

    async def test_strict_types(self):
        for changes in ({'message': 12}, {'message': True}, {'user_id': 12}, {'context_id': None},
                        {'schema_contract': []}):
            self.error(await self.post(raw(**changes)), 422, 'INVALID_REQUEST')

    async def test_invalid_uuid(self):
        for user in ('not-a-uuid', USER.replace('-', ''), USER.upper().replace('000001', '00000A')):
            self.error(await self.post(raw(user_id=user)), 422, 'INVALID_REQUEST')

    async def test_context_not_supported(self):
        self.error(await self.post(raw(context_id='previous')), 422, 'CONTEXT_NOT_SUPPORTED')

    async def test_message_utf16_boundary(self):
        self.assertEqual((await self.post(raw(message='😀'*2000))).status_code, 200)
        self.error(await self.post(raw(message='😀'*2000+'a')), 422, 'INVALID_REQUEST')

    async def test_blank_message(self):
        self.error(await self.post(raw(message=' \n\t')), 422, 'INVALID_REQUEST')

    async def test_wrong_schema_types(self):
        identity = dict(payload()['schema_contract'], schema_sha256=True)
        self.error(await self.post(raw(schema_contract=identity)), 422, 'INVALID_REQUEST')

    async def test_liveness_local_only_and_minimal(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app, client=('127.0.0.1', 1234)),
                                     base_url='http://fixture') as local:
            response = await local.get('/v1/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'contract_version': 'h1-read-v1.0', 'status': 'alive'})
        self.assertEqual(response.headers['cache-control'], 'no-store')

    async def test_liveness_remote_requires_auth(self):
        self.error(await self.client.get('/v1/health'), 401, 'AUTH_REQUIRED')
        response = await self.client.get('/v1/health', headers={'Authorization': 'Bearer '+QUERY_TOKEN})
        self.assertEqual(response.status_code, 200)

    async def test_forwarded_loopback_does_not_bypass_auth(self):
        response = await self.client.get('/v1/health', headers={'X-Forwarded-For': '127.0.0.1',
                                                               'X-Real-IP': '::1'})
        self.error(response, 401, 'AUTH_REQUIRED')

    async def test_readiness_requires_auth_even_local(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app, client=('::1', 1234)),
                                     base_url='http://fixture') as local:
            response = await local.get('/v1/health?mode=ready&capability=query-v1')
        self.error(response, 401, 'AUTH_REQUIRED')

    async def test_readiness_query_unavailable(self):
        response = await self.client.get('/v1/health?mode=ready&capability=query-v1',
                                         headers={'Authorization': 'Bearer '+QUERY_TOKEN})
        self.error(response, 503, 'NOT_READY')
        self.assertEqual(response.json()['status'], 'unavailable')
        self.assertEqual(response.json()['provider_transport'], 'not_probed')
        self.assertEqual(response.json()['production_write'], 'blocked')

    async def test_readiness_inspect_unavailable(self):
        response = await self.client.get('/v1/health?mode=ready&capability=retrieve',
                                         headers={'Authorization': 'Bearer '+INSPECT_TOKEN})
        self.error(response, 503, 'NOT_READY')

    async def test_readiness_scope_denied(self):
        response = await self.client.get('/v1/health?mode=ready&capability=retrieve',
                                         headers={'Authorization': 'Bearer '+QUERY_TOKEN})
        self.error(response, 403, 'SCOPE_DENIED')

    async def test_health_strict_query_parameters(self):
        for query in ('mode=ready', 'mode=ready&capability=unknown', 'mode=unknown',
                      'mode=ready&mode=ready&capability=query-v1', 'extra=1'):
            self.error(await self.client.get('/v1/health?'+query,
                                            headers={'Authorization': 'Bearer '+QUERY_TOKEN}),
                       422, 'INVALID_REQUEST')

    async def test_no_public_query_or_debug_or_docs_routes(self):
        app = shell.create_app(shell.ApiSettings())
        self.assertEqual({route.path for route in app.routes}, {'/v1/health'})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://fixture') as client:
            for path in ('/v1/query', '/v1/retrieve', '/v1/query/stream', '/v1/jobs',
                         '/v1/benchmarks', '/v1/graph/release', '/_admission', '/docs', '/redoc', '/openapi.json'):
                self.assertEqual((await client.get(path)).status_code, 404)
            unsupported = await client.post('/v1/health', content=b'{}')
            self.assertEqual(unsupported.status_code, 405)
            self.assertEqual(unsupported.headers.get('allow'), 'GET')

    async def test_error_and_logs_sanitized(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger = logging.getLogger()
        logger.addHandler(handler)
        try:
            response = await self.client.get('/_error')
        finally:
            logger.removeHandler(handler)
        self.error(response, 500, 'INTERNAL_ERROR')
        for forbidden in (QUERY_TOKEN, 'private-secret', 'provider endpoint', 'Traceback'):
            self.assertNotIn(forbidden, stream.getvalue())

    async def test_http_exception_detail_sanitized(self):
        self.error(await self.client.get('/_http_error'), 400, 'INVALID_REQUEST')
        @self.app.get('/_method_error', include_in_schema=False)
        async def method_failed():
            raise HTTPException(status_code=405, detail='private-secret',
                                headers={'Allow': 'GET', 'X-Private': QUERY_TOKEN})
        response = await self.client.get('/_method_error')
        self.error(response, 405, 'INVALID_REQUEST')
        self.assertEqual(response.headers.get('allow'), 'GET')
        self.assertNotIn('x-private', response.headers)

    async def test_request_id_is_server_generated(self):
        response = await self.post(headers={'X-Request-ID': 'private-secret'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(UUID(response.headers['x-request-id'])), response.headers['x-request-id'])

    async def test_upload_timeout_sanitized(self):
        async def timeout(*args, **kwargs):
            args[0].close()
            raise asyncio.TimeoutError()
        with patch.object(security.asyncio, 'wait_for', side_effect=timeout):
            response = await self.post()
        self.error(response, 504, 'QUERY_TIMEOUT')

    async def test_startup_shutdown_do_not_initialize_runtime(self):
        async with self.app.router.lifespan_context(self.app):
            self.assertEqual((await self.post()).status_code, 200)
            self.factory.assert_not_called()

    async def test_fresh_shell_import_does_not_load_core_or_registry(self):
        code = '''
import sys
from unittest.mock import Mock
from kag.http_api.app import create_app, ApiSettings
factory = Mock(side_effect=AssertionError('runtime constructor'))
app = create_app(ApiSettings(), runtime_factory=factory)
assert not factory.called
for name in ('kag.bootstrap','kag.legal_solver','kag.retriever','kag.common.registry','knext'):
    assert name not in sys.modules, name
assert {r.path for r in app.routes} == {'/v1/health'}
print('SHELL_IMPORT_PASS; runtime_factory=0; core=0; registry=0')
'''
        result = subprocess.run([sys.executable, '-B', '-c', code], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('SHELL_IMPORT_PASS', result.stdout)

    async def test_missing_peer_is_not_local(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app, client=None),
                                     base_url='http://fixture') as client:
            response = await client.get('/v1/health')
        self.error(response, 401, 'AUTH_REQUIRED')

    async def test_ipv6_loopback_and_hostname_not_trusted(self):
        for host, expected in (('::1', 200), ('localhost', 401)):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app, client=(host, 1234)),
                                         base_url='http://fixture') as client:
                self.assertEqual((await client.get('/v1/health')).status_code, expected)

    async def test_duplicate_content_encoding(self):
        response = await self.client.post('/_admission', content=raw(), headers=[
            ('Authorization', 'Bearer '+QUERY_TOKEN), ('Content-Type', 'application/json'),
            ('Content-Encoding', 'identity'), ('Content-Encoding', 'identity')])
        self.error(response, 415, 'UNSUPPORTED_MEDIA_TYPE')

    async def test_duplicate_content_length(self):
        response = await self.client.post('/_admission', content=raw(), headers=[
            ('Authorization', 'Bearer '+QUERY_TOKEN), ('Content-Type', 'application/json'),
            ('Content-Length', str(len(raw()))), ('Content-Length', str(len(raw())))])
        self.error(response, 422, 'INVALID_REQUEST')

    async def test_ambiguous_transfer_encoding_and_length(self):
        self.error(await self.post(headers={'Transfer-Encoding': 'chunked'}), 422, 'INVALID_REQUEST')

    async def test_disconnect_before_complete_upload(self):
        from starlette.requests import ClientDisconnect
        async def chunks():
            yield b'{'
            raise ClientDisconnect()
        self.error(await self.post(chunks()), 422, 'INVALID_REQUEST')

    async def test_unsupported_dto_cannot_use_permissive_parser(self):
        @self.app.post('/_wrong_dto', include_in_schema=False)
        async def wrong(request: Request):
            return await security.admit_request(request, 'query', dict)
        response = await self.client.post('/_wrong_dto', content=raw(), headers={
            'Authorization': 'Bearer '+QUERY_TOKEN, 'Content-Type': 'application/json'})
        self.error(response, 503, 'NOT_READY')

    async def test_upstream_registry_unchanged_by_shell_lifecycle(self):
        code = '''
import asyncio, sys
def audit(event, args):
    if event in ('socket.connect','socket.getaddrinfo'):
        raise AssertionError('network prohibited')
sys.addaudithook(audit)
from kag.bootstrap import initialize
initialize()
from kag.common.registry import Registrable
registry=Registrable._registry
before={abc:dict(values) for abc,values in registry.items()}
from kag.http_api.app import create_app, ApiSettings
app=create_app(ApiSettings())
async def lifecycle():
    async with app.router.lifespan_context(app):
        assert Registrable._registry is registry
asyncio.run(lifecycle())
assert Registrable._registry is registry
assert before==dict(registry)
print('REGISTRY_UNCHANGED; entries='+str(sum(len(v) for v in registry.values())))
'''
        result = subprocess.run([sys.executable, '-B', '-c', code], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('REGISTRY_UNCHANGED', result.stdout)


if __name__ == '__main__':
    unittest.main()
