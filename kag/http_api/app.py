"""Verified v1 HTTP adapter; independent live authorities remain unavailable."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from ipaddress import ip_address
import os
import math
from pathlib import Path
import time
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, Response

from .contract import ApiFailure
from . import artifacts, contract
from .security import ServiceSecrets, admit_request, authorize, request_principal


@dataclass(frozen=True)
class ApiSettings:
    secrets: ServiceSecrets = field(default_factory=ServiceSecrets, repr=False)

    def __post_init__(self):
        if type(self.secrets) is not ServiceSecrets:
            raise ApiFailure('NOT_READY')

    @classmethod
    def from_env(cls):
        def tokens(prefix):
            result = []
            for suffix in ('SECRET_FILE', 'PREVIOUS_SECRET_FILE'):
                path = os.environ.get(prefix+suffix)
                if path is None:
                    continue
                try:
                    with Path(path).open('rb') as stream:
                        raw = stream.read(515)
                    if len(raw) > 514:
                        raise ApiFailure('NOT_READY')
                    if raw.endswith(b'\r\n'):
                        raw = raw[:-2]
                    elif raw.endswith(b'\n'):
                        raw = raw[:-1]
                    result.append(raw.decode('ascii', errors='strict'))
                except (OSError, UnicodeError, ValueError):
                    raise ApiFailure('NOT_READY') from None
            return tuple(result)
        return cls(ServiceSecrets(tokens('KAG_HTTP_QUERY_'), tokens('KAG_HTTP_INSPECT_')))


def _failure(request: Request, code: str, *, status=None, extra=None):
    failure = ApiFailure(code)
    body = {'request_id': request.state.request_id,
            'error': {'code': failure.code, 'message': failure.message, 'retryable': failure.retryable},
            'native_state': failure.native_state}
    if extra:
        body.update(extra)
    response_status = failure.status if status is None else status
    headers = {'WWW-Authenticate':'Bearer'} if response_status == 401 else (
        {'Retry-After':'1'} if failure.code == 'CONCURRENCY_LIMIT' else None)
    return JSONResponse(body,status_code=response_status,headers=headers)


class _SafeHTTP:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        scope.setdefault('state', {})['request_id'] = str(uuid4())
        started = False

        async def authority():
            if time.monotonic() >= scope['state']['h1_deadline']:
                raise ApiFailure('QUERY_TIMEOUT')
            if scope['state'].get('h1_query_verified'):
                from .runtime import _today
                if _today() != scope['state']['h1_as_of']:
                    raise ApiFailure('DATE_BOUNDARY_CHANGED')
            try:
                await asyncio.wait_for(asyncio.to_thread(scope['state']['h1_authority_guard']),
                    scope['state']['h1_deadline']-time.monotonic())
            except asyncio.TimeoutError:
                raise ApiFailure('QUERY_TIMEOUT') from None

        async def safe_send(message):
            nonlocal started
            verified = scope['state'].get('h1_query_verified') or scope['state'].get('h1_retrieve_verified')
            if verified:
                await authority()
            if message['type'] == 'http.response.start':
                started = True
                headers = [(k, v) for k, v in message.get('headers', [])
                           if k.lower() not in (b'x-request-id', b'cache-control')]
                message = {**message, 'headers': headers+[
                    (b'x-request-id', scope['state']['request_id'].encode('ascii')),
                    (b'cache-control', b'no-store')]}
            if verified:
                midnight_deadline = scope['state']['h1_deadline']
                if scope['state'].get('h1_query_verified'):
                    now = datetime.now(ZoneInfo('Asia/Saigon'))
                    midnight = datetime.combine(now.date()+timedelta(days=1),datetime.min.time(),now.tzinfo)
                    midnight_deadline = time.monotonic()+(midnight-now).total_seconds()
                delivery = asyncio.create_task(send(message))
                try:
                    while not delivery.done():
                        left = min(scope['state']['h1_deadline'],midnight_deadline)-time.monotonic()
                        if left <= 0:
                            raise ApiFailure('DATE_BOUNDARY_CHANGED' if midnight_deadline < scope['state']['h1_deadline']
                                             else 'QUERY_TIMEOUT')
                        await asyncio.wait({delivery},timeout=min(.02,left))
                        if not delivery.done():
                            await authority()
                    delivery.result()
                finally:
                    if not delivery.done():
                        delivery.cancel()
                    await asyncio.gather(delivery,return_exceptions=True)
            else:
                await send(message)

        try:
            await self.app(scope, receive, safe_send)
        except ApiFailure as exc:
            if not started:
                scope['state']['h1_query_verified'] = False
                scope['state']['h1_retrieve_verified'] = False
                response = _failure(Request(scope), exc.code)
                await response(scope, receive, safe_send)
        except Exception:
            if not started:
                scope['state']['h1_query_verified'] = False
                scope['state']['h1_retrieve_verified'] = False
                response = _failure(Request(scope), 'INTERNAL_ERROR')
                await response(scope, receive, safe_send)


def _local(request: Request) -> bool:
    try:
        return request.client is not None and ip_address(request.client.host).is_loopback
    except ValueError:
        return False


def _verify_retrieve_items(items, release, reader):
    from kag.vector_contract import TARGETS
    if type(items) is not list:
        raise ApiFailure('INVALID_NATIVE_RESULT')
    if len(items) > 110:
        raise ApiFailure('RESULT_LIMIT_EXCEEDED')
    try:
        contract._json_value(items)
    except (ValueError,RecursionError):
        raise ApiFailure('INVALID_NATIVE_RESULT') from None
    catalog = {}
    relations = set()
    schema = artifacts._json(release.contract_bytes)
    for record in release.records:
        catalog.setdefault((record.entity_type,record.entity_id),{})[record.field] = record
        for relation in record.graph_context:
            relations.add((tuple(relation['from']),relation['predicate'],tuple(relation['to'])))
    indexes = reader.indexes()
    fields = {'entity_type','entity_id','doc_id','unit_id','sign_id','source_texts',
              'score','vector_sources','graph_context'}
    def score(value):
        return type(value) in (int,float) and 0<=value<=1 and math.isfinite(value)
    seen = set()
    for item in items:
        if (type(item) is not dict or set(item)!=fields
                or any(not contract._text(item[k]) or not item[k] for k in ('entity_type','entity_id'))
                or type(item['source_texts']) is not dict or type(item['vector_sources']) is not list
                or type(item['graph_context']) is not list
                or (item['score'] is not None and not score(item['score']))):
            raise ApiFailure('INVALID_NATIVE_RESULT')
        key = item['entity_type'],item['entity_id']
        records = catalog.get(key)
        if not records:
            raise ApiFailure('SOURCE_VALIDATION_FAILED')
        reference = next(iter(records.values()))
        if (any(item[k]!=getattr(reference,k) for k in ('doc_id','unit_id','sign_id'))
                or key in seen):
            raise ApiFailure('SOURCE_VALIDATION_FAILED')
        seen.add(key)
        kind = key[0].removeprefix(release.schema_contract.namespace+'.')
        targets = dict(TARGETS[kind])
        # Catalog metadata uses logical names; native preserves physical names and empty Text.
        texts = {row['schema_name']:reference.metadata.get(row['logical_name'])
                 for row in schema['node_properties'][kind] if row['schema_name'] in targets}
        if (set(item['source_texts'])!=set(targets)
                or item['source_texts']!=texts):
            raise ApiFailure('SOURCE_VALIDATION_FAILED')
        properties = set()
        for source in item['vector_sources']:
            if (type(source) is not dict or set(source)!={'property','score','index'}
                    or not contract._text(source['property']) or not score(source['score'])
                    or not contract._text(source['index']) or not source['index']):
                raise ApiFailure('INVALID_NATIVE_RESULT')
            prop = source['property']
            if prop not in targets or prop in properties:
                raise ApiFailure('SOURCE_VALIDATION_FAILED')
            properties.add(prop)
            matched = [i for i in indexes if i.get('labelsOrTypes')==[key[0]]
                       and i.get('properties')==[targets[prop]] and i.get('type')=='VECTOR']
            if len(matched)!=1 or matched[0].get('name')!=source['index']:
                raise ApiFailure('SOURCE_VALIDATION_FAILED')
        if ((item['score'] is None) != (not item['vector_sources'])
                or (item['vector_sources'] and item['score']!=max(s['score'] for s in item['vector_sources']))
                or (item['score'] is None and not item['graph_context'])):
            raise ApiFailure('INVALID_NATIVE_RESULT')
        contexts = set()
        for relation in item['graph_context']:
            if (type(relation) is not dict or set(relation)!={'from','predicate','to'}
                    or not contract._text(relation['predicate'])
                    or any(type(relation[s]) is not list or len(relation[s])!=2
                           or any(not contract._text(v) or not v for v in relation[s]) for s in ('from','to'))):
                raise ApiFailure('INVALID_NATIVE_RESULT')
            source,target = tuple(relation['from']),tuple(relation['to'])
            identity = source,relation['predicate'],target
            if (identity not in relations or key not in (source,target)
                    or source not in catalog or target not in catalog or identity in contexts):
                raise ApiFailure('SOURCE_VALIDATION_FAILED')
            contexts.add(identity)


def create_app(settings: ApiSettings | None = None, runtime_factory=None, *, enable_sample_routes=False) -> FastAPI:
    if type(enable_sample_routes) is not bool:
        raise ApiFailure('NOT_READY')
    settings = ApiSettings.from_env() if settings is None else settings
    if type(settings) is not ApiSettings:
        raise ApiFailure('NOT_READY')

    @asynccontextmanager
    async def lifespan(application):
        from .runtime import RuntimeSupervisor, initialize_runtime
        application.state.runtime_supervisor = RuntimeSupervisor()
        try:
            initialize_runtime()
        except Exception:
            application.state.runtime_supervisor.closed = True
        try:
            yield
        finally:
            await application.state.runtime_supervisor.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None, debug=False)
    app.state.http_settings = settings
    app.state.runtime_factory = runtime_factory
    app.state.serving_release = None
    app.state.runtime_settings = None
    app.add_middleware(_SafeHTTP)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        response = _failure(request, 'INVALID_REQUEST', status=exc.status_code
                            if exc.status_code in (400, 404, 405, 422) else 500)
        if exc.status_code == 405 and exc.headers:
            allow = exc.headers.get('Allow', '')
            if (type(allow) is str and len(allow) <= 64
                    and all(method in {'GET', 'HEAD', 'POST', 'OPTIONS'} for method in allow.split(', '))):
                response.headers['Allow'] = allow
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return _failure(request, 'INVALID_REQUEST')

    @app.get('/v1/health')
    async def health(request: Request):
        params = list(request.query_params.multi_items())
        principal = None if not params and _local(request) else request_principal(request)
        if not params:
            return {'contract_version': 'h1-read-v1.0', 'status': 'alive'}
        if (len(params) != 2 or dict(params).get('mode') != 'ready'
                or set(dict(params)) != {'mode', 'capability'}
                or dict(params)['capability'] not in ('retrieve', 'query-v1')):
            raise ApiFailure('INVALID_REQUEST')
        capability = dict(params)['capability']
        authorize(principal, 'inspect' if capability == 'retrieve' else 'query', None)
        supervisor = getattr(app.state, 'runtime_supervisor', None)
        checks = supervisor.readiness() if supervisor is not None else {
            'runtime': 'blocked', 'sources': 'unknown'}
        return _failure(request, 'NOT_READY', extra={
            'status': 'unavailable', 'capability': capability,
            'checks': {'auth': 'pass', **checks},
            'provider_transport': 'not_probed', 'production_write': 'blocked'})

    if not (settings.secrets.query_tokens or settings.secrets.inspect_tokens):
        return app

    @app.get('/v1/graph/release')
    async def graph_release(request: Request):
        principal = request_principal(request)
        authorize(principal,'query' if 'query' in principal.scopes else 'inspect',None)
        if request.query_params:
            raise ApiFailure('INVALID_REQUEST')
        release = app.state.serving_release
        if type(release) is not artifacts.ServingRelease:
            raise ApiFailure('RELEASE_UNAVAILABLE')
        try:
            await asyncio.to_thread(artifacts._unchanged,release)
        except Exception:
            raise ApiFailure('RELEASE_UNAVAILABLE') from None
        return artifacts.release_view(release)

    async def verified_query(request: Request, *, stream=False):
        from . import runtime as core
        release, settings = app.state.serving_release, app.state.runtime_settings
        supervisor = getattr(app.state,'runtime_supervisor',None)
        if (type(release) is not artifacts.ServingRelease or settings is None or supervisor is None):
            await admit_request(request,'query')
            if request.query_params:
                raise ApiFailure('INVALID_REQUEST')
            raise ApiFailure('RELEASE_UNAVAILABLE' if type(release) is not artifacts.ServingRelease else 'NOT_READY')
        if settings.secrets != app.state.http_settings.secrets:
            await admit_request(request,'query')
            raise ApiFailure('NOT_READY')

        async def finalize(instance, result, parsed):
            def identity():
                instance.budget.response_remaining()
                if core._today() != instance.as_of:
                    raise ApiFailure('DATE_BOUNDARY_CHANGED')
                selected = app.state.serving_release
                if type(selected) is not artifacts.ServingRelease:
                    raise ApiFailure('RELEASE_UNAVAILABLE')
                if selected.schema_contract != release.schema_contract:
                    raise ApiFailure('SCHEMA_CONTRACT_MISMATCH')
                if selected.descriptor['source_snapshot_id'] != release.descriptor['source_snapshot_id']:
                    raise ApiFailure('SOURCE_SNAPSHOT_MISMATCH')
                if (selected.release_id != release.release_id or selected.descriptor_sha256 != release.descriptor_sha256
                        or app.state.runtime_settings != settings):
                    raise ApiFailure('RELEASE_MISMATCH')
                try:
                    schema_root = Path(__file__).resolve().parents[1]/'schema'
                    if (artifacts._sha(artifacts._read(schema_root,'VietRoadTraffic.schema')) != release.schema_contract.schema_sha256
                            or artifacts._read(schema_root,'schema_contract.json') != release.contract_bytes):
                        raise ApiFailure('SCHEMA_CONTRACT_MISMATCH')
                    if artifacts._read(release.root,'release.json') != dict(release.artifacts)['release.json']:
                        raise ApiFailure('RELEASE_MISMATCH')
                    core._identity(request,settings,release,parsed,instance.as_of)
                except core.RuntimeFailure as exc:
                    raise ApiFailure(exc.code) from None
                except artifacts.ArtifactFailure as exc:
                    raise ApiFailure('RELEASE_UNAVAILABLE' if exc.state is artifacts.VerificationState.UNAVAILABLE
                                     else 'SOURCE_VALIDATION_FAILED') from None
                except OSError:
                    raise ApiFailure('RELEASE_UNAVAILABLE') from None
                instance.budget.response_remaining()

            def sources():
                identity()
                try:
                    verified = artifacts.verify_native_sources(result,release,instance.reader,
                        instance.as_of,settings.webapp_snapshot_id)
                except artifacts.ArtifactFailure as exc:
                    identity()
                    if exc.state is artifacts.VerificationState.UNAVAILABLE:
                        raise ApiFailure('BACKEND_UNAVAILABLE') from None
                    raise ApiFailure(exc.code if exc.code == 'INVALID_NATIVE_RESULT' else 'SOURCE_VALIDATION_FAILED') from None
                if (verified.state is not artifacts.VerificationState.VERIFIED
                        or verified.publication_state is not artifacts.VerificationState.VERIFIED
                        or (verified.release_id,verified.source_snapshot_id,verified.schema_contract,
                            verified.release_descriptor_sha256,verified.as_of,verified.webapp_snapshot_id)
                        != (release.release_id,settings.source_snapshot_id,release.schema_contract,
                            release.descriptor_sha256,instance.as_of,settings.webapp_snapshot_id)):
                    raise ApiFailure('SOURCE_VALIDATION_FAILED')
                identity()
                return verified

            def verified_bytes():
                verified = sources()
                payload = contract.project_v1(result,verified)
                try:
                    raw = contract.encode_v1(payload)
                except ApiFailure as exc:
                    if exc.code == 'V1_RESULT_UNREPRESENTABLE':
                        raise ApiFailure('RESULT_LIMIT_EXCEEDED') from None
                    raise
                if stream:
                    raw = b'event: done\ndata: '+raw+b'\n\n'
                    if len(raw) > 245760:
                        raise ApiFailure('RESULT_LIMIT_EXCEEDED')
                if sources() != verified:
                    raise ApiFailure('SOURCE_VALIDATION_FAILED')
                request.state.h1_authority_guard = identity
                return raw, {'X-KAG-Release-ID':release.release_id,
                    'X-WebApp-Snapshot-ID':settings.webapp_snapshot_id,'X-KAG-As-Of':instance.as_of.isoformat()},instance.as_of
            return await asyncio.to_thread(verified_bytes)

        watching = True
        async def disconnected():
            while watching:
                if (hasattr(request.state,'delegated_user_id') and await request.is_disconnected()):
                    return True
                await asyncio.sleep(.02)

        operation = asyncio.create_task(supervisor.query(request,settings,release,
            finalize=finalize,factory=app.state.runtime_factory))
        watcher = asyncio.create_task(disconnected())
        try:
            done,_ = await asyncio.wait({operation,watcher},return_when=asyncio.FIRST_COMPLETED)
            if watcher in done and watcher.result():
                raise asyncio.CancelledError
            raw,headers,as_of = operation.result()
            if core._today() != as_of:
                raise ApiFailure('DATE_BOUNDARY_CHANGED')
            if time.monotonic() >= request.state.h1_deadline:
                raise ApiFailure('QUERY_TIMEOUT')
            request.state.h1_query_verified, request.state.h1_as_of = True, as_of
            if stream:
                headers['X-Accel-Buffering'] = 'no'
                return Response(raw,media_type='text/event-stream',headers=headers)
            return Response(raw,media_type='application/json',headers=headers)
        except core.RuntimeFailure as exc:
            raise ApiFailure(exc.code) from None
        finally:
            watching = False
            for task in (operation,watcher):
                if not task.done():
                    task.cancel()
            await asyncio.gather(operation,watcher,return_exceptions=True)

    @app.post('/v1/query')
    async def query(request: Request):
        return await verified_query(request)

    if enable_sample_routes:
        @app.post('/v1/query/stream')
        async def query_stream(request: Request):
            return await verified_query(request,stream=True)

        @app.post('/v1/retrieve')
        async def retrieve(request: Request):
            from . import runtime as core
            release, settings = app.state.serving_release, app.state.runtime_settings
            supervisor = getattr(app.state,'runtime_supervisor',None)
            if type(release) is not artifacts.ServingRelease or settings is None or supervisor is None:
                await admit_request(request,'inspect',contract.RetrieveRequest)
                if request.query_params:
                    raise ApiFailure('INVALID_REQUEST')
                raise ApiFailure('RELEASE_UNAVAILABLE' if type(release) is not artifacts.ServingRelease else 'NOT_READY')
            if settings.secrets != app.state.http_settings.secrets:
                await admit_request(request,'inspect',contract.RetrieveRequest)
                raise ApiFailure('NOT_READY')

            async def finalize(instance, result, parsed):
                def identity():
                    instance.budget.response_remaining()
                    selected = app.state.serving_release
                    if type(selected) is not artifacts.ServingRelease:
                        raise ApiFailure('RELEASE_UNAVAILABLE')
                    if selected.schema_contract != release.schema_contract:
                        raise ApiFailure('SCHEMA_CONTRACT_MISMATCH')
                    if selected.descriptor['source_snapshot_id'] != release.descriptor['source_snapshot_id']:
                        raise ApiFailure('SOURCE_SNAPSHOT_MISMATCH')
                    if (selected.release_id != release.release_id or selected.descriptor_sha256 != release.descriptor_sha256
                            or app.state.runtime_settings != settings or app.state.http_settings.secrets != settings.secrets):
                        raise ApiFailure('RELEASE_MISMATCH')
                    try:
                        if artifacts._read(release.root,'release.json') != dict(release.artifacts)['release.json']:
                            raise ApiFailure('RELEASE_MISMATCH')
                        core._identity(request,settings,release,parsed,capability='retrieve')
                    except core.RuntimeFailure as exc:
                        raise ApiFailure(exc.code) from None
                    except artifacts.ArtifactFailure as exc:
                        raise ApiFailure('BACKEND_UNAVAILABLE' if exc.state is artifacts.VerificationState.UNAVAILABLE
                                         else 'SOURCE_VALIDATION_FAILED') from None
                    instance.budget.response_remaining()

                def sources():
                    identity()
                    try:
                        artifacts._backend(instance.reader,release)
                        artifacts._readback(instance.reader,release.records,artifacts._json(release.contract_bytes))
                        _verify_retrieve_items(result,release,instance.reader)
                        artifacts._backend(instance.reader,release)
                        artifacts._unchanged(release)
                    except artifacts.ArtifactFailure as exc:
                        raise ApiFailure('BACKEND_UNAVAILABLE' if exc.state is artifacts.VerificationState.UNAVAILABLE
                                         else 'SOURCE_VALIDATION_FAILED') from None
                    identity()

                def verified_bytes():
                    sources()
                    payload = {'contract_version':'h1-read-v1.1','request_id':request.state.request_id,
                        'release_id':release.release_id,'source_snapshot_id':settings.source_snapshot_id,
                        'schema_contract':asdict(release.schema_contract),'items':result}
                    raw = contract.encode_retrieve(payload)
                    sources()
                    request.state.h1_authority_guard = identity
                    return raw
                return await asyncio.to_thread(verified_bytes)

            watching = True
            async def disconnected():
                while watching:
                    if getattr(request,'_stream_consumed',False) and await request.is_disconnected():
                        return True
                    await asyncio.sleep(.02)
            operation = asyncio.create_task(supervisor.retrieve(request,settings,release,
                finalize=finalize,factory=app.state.runtime_factory))
            watcher = asyncio.create_task(disconnected())
            try:
                done,_ = await asyncio.wait({operation,watcher},return_when=asyncio.FIRST_COMPLETED)
                if watcher in done and watcher.result():
                    raise asyncio.CancelledError
                raw = operation.result()
                if time.monotonic() >= request.state.h1_deadline:
                    raise ApiFailure('QUERY_TIMEOUT')
                request.state.h1_retrieve_verified = True
                return Response(raw,media_type='application/json',headers={'X-KAG-Release-ID':release.release_id})
            except core.RuntimeFailure as exc:
                raise ApiFailure(exc.code) from None
            finally:
                watching = False
                for task in (operation,watcher):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(operation,watcher,return_exceptions=True)

    return app
