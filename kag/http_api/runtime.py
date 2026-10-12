"""Request-owned Core adapter. Live serving remains denied without operational proof.

No HTTP inference routes, provider probes, registry registrations or write clients.
"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
import inspect
import logging
import math
import re
from pathlib import Path
import platform
import sys
import threading
import time
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx

from .app import ApiSettings
from .artifacts import (ArtifactFailure, ServingRelease, VerificationState,
                        _backend, _json, _readback, _unchanged, load_sample_proof,
                        verify_sample_backend, sample_source_vector)
from .contract import ApiFailure, RetrieveRequest, SampleVectorRequest
from .security import admit_request, authorize, request_principal

REQUEST_SECONDS = 25.0
TRANSPORT_SECONDS = 5.0
_CURRENT = ContextVar('h1_admitted_runtime', default=None)


class RuntimeFailure(Exception):
    """Fixed internal errors; public HTTP mapping belongs to Step5."""
    _ERRORS = {
        'CONCURRENCY_LIMIT': (429, 'Request capacity unavailable.'),
        'SCHEMA_CONTRACT_MISMATCH': (409, 'Contract identity mismatch.'),
        'RELEASE_MISMATCH': (409, 'Release identity mismatch.'),
        'SOURCE_SNAPSHOT_MISMATCH': (409, 'Source snapshot identity mismatch.'),
        'DATE_MISMATCH': (409, 'Request date mismatch.'),
        'PROVIDER_ERROR': (502, 'Inference unavailable.'),
    }

    def __init__(self, code):
        self.status, self.message = self._ERRORS[code]
        self.code = code
        self.retry_after = 1 if code == 'CONCURRENCY_LIMIT' else None
        super().__init__(self.message)


@dataclass(frozen=True, repr=False)
class RuntimeSettings(ApiSettings):
    """Trusted process configuration, separate from request DTOs and env secrets."""
    release_id: str | None = None
    source_snapshot_id: str | None = None
    webapp_snapshot_id: str | None = None
    reader_username: str | None = None
    reader_password: str | None = None
    embedding_url: str | None = None
    embedding_model: str | None = None
    embedding_key: str | None = None
    chat_url: str | None = None
    chat_model: str | None = None
    chat_key: str | None = None
    sample_proof_sha256: str | None = None
    broker_url: str | None = None
    broker_token: str | None = None
    query_proof_sha256: str | None = None
    provider_gateway: str | None = None
    provider_gateway_token: str | None = None
    attempt_ledger: str | None = None
    development_policy: dict | None = None


class _Budget:
    def __init__(self, deadline, clock=time.monotonic):
        if type(deadline) not in (float,int) or not math.isfinite(deadline):
            raise ApiFailure('NOT_READY')
        self.deadline, self.clock = deadline, clock
        self.stopped = threading.Event()
        self.finished = False
        self.transport_seconds = TRANSPORT_SECONDS

    def remaining(self):
        if self.finished:
            raise ApiFailure('NOT_READY')
        return self.response_remaining()

    def response_remaining(self):
        left = self.deadline-self.clock()
        if self.stopped.is_set() or left <= 0:
            raise ApiFailure('QUERY_TIMEOUT')
        return left

    def stop(self):
        self.stopped.set()


class _ReaderBoundary:
    def __init__(self, opener, budget):
        self.opener, self.budget = opener, budget

    def open(self, request, *, timeout):
        return self.opener.open(request,timeout=min(timeout,TRANSPORT_SECONDS,self.budget.remaining()))

    def close(self):
        close = getattr(self.opener,'close',None)
        if callable(close):
            close()


def _timeout(request, budget):
    remaining = min(getattr(budget,'transport_seconds',TRANSPORT_SECONDS),budget.remaining())
    request.extensions['timeout'] = {'connect':min(2.0,remaining),
        'read':remaining,'write':remaining,'pool':remaining}


class _DeadlineTransport(httpx.BaseTransport):
    def __init__(self, transport, budget):
        self.transport, self.budget = transport, budget

    def handle_request(self, request):
        _timeout(request,self.budget)
        return self.transport.handle_request(request)

    def close(self):
        self.transport.close()


class _AsyncDeadlineTransport(httpx.AsyncBaseTransport):
    def __init__(self, transport, budget):
        self.transport, self.budget = transport, budget

    async def handle_async_request(self, request):
        _timeout(request,self.budget)
        return await self.transport.handle_async_request(request)

    async def aclose(self):
        await self.transport.aclose()


def _guard_sdk(model, budget):
    # SDK retries and proxy mounts must all traverse the same request deadline.
    for name, client_type, guard in (('client',httpx.Client,_DeadlineTransport),
                                     ('aclient',httpx.AsyncClient,_AsyncDeadlineTransport)):
        sdk = getattr(model,name)
        client = sdk._client
        if not isinstance(client,client_type):
            raise ApiFailure('NOT_READY')
        client._transport = guard(client._transport,budget)
        client._mounts = {pattern:guard(transport,budget) if transport else None
                          for pattern,transport in client._mounts.items()}


def initialize_runtime():
    """Bootstrap identity only; no dependency construction or remote probe."""
    if (sys.version_info[:3] != (3,10,16) or platform.system() != 'Linux'
            or platform.machine() != 'x86_64'):
        raise ApiFailure('NOT_READY')
    from kag.bootstrap import initialize
    initialize()
    from kag.common.registry import Registrable
    from kag.solver.pipeline.kag_iterative_pipeline import KAGIterativePipeline
    vendor = Path(__file__).resolve().parents[2]/'vendor/KAG'
    if any(not Path(inspect.getfile(cls)).resolve().is_relative_to(vendor)
           for cls in (Registrable,KAGIterativePipeline)):
        raise ApiFailure('NOT_READY')
    for name, logger in logging.Logger.manager.loggerDict.items():
        if isinstance(logger,logging.Logger) and name.startswith(('kag.','knext.','openai','httpx','httpcore')):
            logger.disabled = True


def _today():
    return datetime.now(ZoneInfo('Asia/Saigon')).date()


def _require_configuration(settings, *, capability='query'):
    if type(settings) is not RuntimeSettings or capability not in ('query','retrieve','retrieve-vector'):
        raise ApiFailure('NOT_READY')
    if settings.development_policy is not None and not settings.query_proof_sha256:
        raise ApiFailure('NOT_READY')
    if settings.query_proof_sha256 and capability in ('query','retrieve'):
        _require_configuration(settings,capability='retrieve-vector')
        fields=('embedding_url','embedding_model','embedding_key','chat_url','chat_model','chat_key',
                'provider_gateway','provider_gateway_token','attempt_ledger','query_proof_sha256')
        for name in fields+(('webapp_snapshot_id',) if capability=='query' else ()):
            value=getattr(settings,name)
            if type(value) is not str or not value.strip() or len(value)>4096:raise ApiFailure('NOT_READY')
        return
    if capability == 'retrieve-vector':
        credentials=('broker_url','broker_token') if settings.broker_url else ('reader_username','reader_password')
        for name in ('release_id','source_snapshot_id','sample_proof_sha256',*credentials):
            value = getattr(settings,name)
            if type(value) is not str or not value.strip() or len(value) > 4096:
                raise ApiFailure('NOT_READY')
        if settings.broker_url:
            if settings.reader_username is not None or settings.reader_password is not None:
                raise ApiFailure('NOT_READY')
        elif settings.reader_username.lower() in ('neo4j','root','admin') or settings.reader_password.lower() in ('dummy','abc123'):
            raise ApiFailure('NOT_READY')
        return
    query_only = {'webapp_snapshot_id','chat_url','chat_model','chat_key'} if capability=='retrieve' else set()
    for name in RuntimeSettings.__dataclass_fields__:
        if name not in ('secrets','sample_proof_sha256','broker_url','broker_token','query_proof_sha256',
                        'provider_gateway','provider_gateway_token','attempt_ledger','development_policy') and name not in query_only:
            value = getattr(settings,name)
            if type(value) is not str or not value.strip() or len(value) > 4096:
                raise ApiFailure('NOT_READY')
    for name in ('embedding_key','reader_password') if capability=='retrieve' else ('embedding_key','chat_key','reader_password'):
        if getattr(settings,name).lower() in ('dummy','abc123'):
            raise ApiFailure('NOT_READY')
    for name in ('embedding_url',) if capability=='retrieve' else ('embedding_url','chat_url'):
        url = httpx.URL(getattr(settings,name))
        if url.scheme not in ('http','https') or not url.host or url.userinfo or url.query or url.fragment:
            raise ApiFailure('NOT_READY')


def _require_operational_proof(settings, release, *, capability='query'):
    if capability == 'retrieve-vector':
        return load_sample_proof(release,settings.sample_proof_sha256,settings.reader_username)
    if settings.query_proof_sha256:
        from .sample_query import load_proof
        from .provider_budget import BudgetError
        try:
            return load_proof(settings,release,capability=capability)
        except BudgetError:
            raise ApiFailure('NOT_READY') from None
    # shortcut: no independent operational attestation available; authorize it separately before live serving.
    raise ArtifactFailure(VerificationState.UNVERIFIED)


def _identity(request, settings, release, parsed, as_of=None, *, capability='query'):
    if type(release) is not ServingRelease:
        raise ApiFailure('NOT_READY')
    if parsed.schema_contract != release.schema_contract:
        raise RuntimeFailure('SCHEMA_CONTRACT_MISMATCH')
    if release.release_id != settings.release_id:
        raise RuntimeFailure('RELEASE_MISMATCH')
    if release.descriptor['source_snapshot_id'] != settings.source_snapshot_id:
        raise RuntimeFailure('SOURCE_SNAPSHOT_MISMATCH')
    if capability in ('retrieve','retrieve-vector'):
        if request.headers.getlist('x-kag-release-id') != [settings.release_id]:
            raise RuntimeFailure('RELEASE_MISMATCH')
        try:
            _unchanged(release)
        except OSError:
            raise ArtifactFailure(VerificationState.UNAVAILABLE) from None
        return None
    as_of = _today() if as_of is None else as_of
    for name, expected, code in (
            ('x-kag-release-id',settings.release_id,'RELEASE_MISMATCH'),
            ('x-webapp-snapshot-id',settings.webapp_snapshot_id,'SOURCE_SNAPSHOT_MISMATCH'),
            ('x-kag-as-of',as_of.isoformat(),'DATE_MISMATCH')):
        values = request.headers.getlist(name)
        if values != [expected]:
            raise RuntimeFailure(code)
    publication = release.publication
    if (publication is None or publication['snapshot_id'] != settings.webapp_snapshot_id
            or publication['as_of'] != as_of.isoformat() or not release.records):
        raise ApiFailure('NOT_READY')
    try:
        _unchanged(release)
    except OSError:
        raise ArtifactFailure(VerificationState.UNAVAILABLE) from None
    return as_of


@dataclass
class RequestRuntime:
    reader: object
    retriever: object
    pipeline: object
    deadline: float
    budget: _Budget = field(repr=False)
    question: str = field(repr=False)
    as_of: object
    sdk_models: list = field(default_factory=list,repr=False)
    closed: bool = False
    capability: str = 'query'
    request_id: str | None = None

    async def close(self):
        if self.closed:
            return
        self.budget.finished = True
        failed = False
        clients = [getattr(model,name,None) for model in self.sdk_models for name in ('client','aclient')]
        clients.append(self.reader if callable(getattr(self.reader,'close',None))
                       else getattr(self.reader,'_opener',None))
        for client in clients:
            close = getattr(client,'close',None)
            if callable(close):
                try:
                    result = close()
                    if inspect.isawaitable(result):
                        await result
                except Exception:
                    failed = True
        self.closed = not failed
        if failed:
            raise ApiFailure('INTERNAL_ERROR')


def _new_reader(settings, release, budget):
    if settings.broker_url:
        from .community import BrokerRetrievalClient
        proof=load_sample_proof(release,settings.sample_proof_sha256,None)
        if proof['broker_url']!=settings.broker_url or settings.reader_username or settings.reader_password:
            raise ApiFailure('NOT_READY')
        reader=BrokerRetrievalClient(release,proof,settings.broker_token,timeout=TRANSPORT_SECONDS)
        reader._opener=_ReaderBoundary(reader._opener,budget)
        return reader
    from kag.retriever.neo4j import Neo4jRetrievalClient
    reader = Neo4jRetrievalClient(release.backend['reader_endpoint'],release.descriptor['database'],
        username=settings.reader_username,password=settings.reader_password,namespace=release.schema_contract.namespace,
        timeout=TRANSPORT_SECONDS)
    reader._opener = _ReaderBoundary(reader._opener,budget)
    return reader


def _sdk_instance(cls, runtime, **kwargs):
    from kag.common.rate_limiter import RATE_LIMITER_MANGER, SYNC_RATE_LIMITER_MANAGER
    managers = (RATE_LIMITER_MANGER,SYNC_RATE_LIMITER_MANAGER)
    key = kwargs.get('name') or cls.generate_key(**kwargs)
    before = [key in manager.limiter_map for manager in managers]
    # Upstream embedding __new__ caches globally; allocate its exact class per request.
    model = object.__new__(cls)
    runtime.sdk_models.append(model)
    try:
        cls.__init__(model,**kwargs)
    finally:
        for manager, existed, attribute in zip(managers,before,('limiter','sync_limiter')):
            if not existed and manager.limiter_map.get(key) is getattr(model,attribute,None):
                manager.limiter_map.pop(key,None)
    _guard_sdk(model,runtime.budget)
    return model


def _embedding_response_metadata(response):
    import base64,json
    response.read()
    try:
        body=response.json()
        rows=body.get('data') if type(body) is dict else None
        value=rows[0].get('embedding') if type(rows) is list and rows and type(rows[0]) is dict else None
        dimension=len(value) if type(value) is list else len(base64.b64decode(value,validate=True))//4 if type(value) is str else None
    except (ValueError,TypeError):
        value=None;dimension=None
    print('SAMPLE_EMBEDDING '+json.dumps(dict(status=response.status_code,
        embedding_type=type(value).__name__,dimension=dimension)),flush=True)


def _new_embedding(settings, runtime):
    from kag.common.vectorize_model.openai_model import OpenAIVectorizeModel
    model = _sdk_instance(OpenAIVectorizeModel,runtime,model=settings.embedding_model,
        api_key=settings.embedding_key,base_url=settings.embedding_url,
        vector_dimensions=3072,timeout=TRANSPORT_SECONDS)
    if settings.query_proof_sha256:
        from .sample_query import configure_model
        configure_model(settings,model,'embedding',component='kag.'+getattr(runtime,'capability','query'),request_id=getattr(runtime,'request_id',None))
        _guard_sdk(model,runtime.budget)
        model.client._client.event_hooks['response'].append(_embedding_response_metadata)
    def embed(question):
        # Vendor vectorize swallows SDK errors and logs source text; keep its guarded client.
        import json
        from kag.vector_contract import valid_vector
        try:
            runtime.budget.remaining()
            response=model.client.embeddings.create(input=question,model=settings.embedding_model)
            vector=response.data[0].embedding if len(response.data)==1 else None
            if not valid_vector(vector,3072):
                raise ValueError('INVALID_VECTOR')
            runtime.budget.remaining()
            return vector
        except Exception as exc:
            print('SAMPLE_EMBEDDING_FAILURE '+json.dumps({'error_type':type(exc).__name__}),flush=True)
            runtime.budget.remaining()
            raise RuntimeFailure('PROVIDER_ERROR') from None
    return embed


def _new_llm(settings, runtime):
    from kag.common.llm.openai_client import OpenAIClient
    model = _sdk_instance(OpenAIClient,runtime,name='h1-'+uuid4().hex,model=settings.chat_model,
        api_key=settings.chat_key,base_url=settings.chat_url,enable_check=False,timeout=TRANSPORT_SECONDS)
    if settings.query_proof_sha256:
        from .sample_query import configure_model, provider_budget, response_model_matches
        configure_model(settings,model,'chat',component='kag.query',request_id=runtime.request_id)
        _guard_sdk(model,runtime.budget)
        responses=[]
        def response_metadata(response):
            import json
            response.read()
            try:
                body=response.json();observed_model=body.get('model')
            except (ValueError,AttributeError,IndexError,TypeError):observed_model=None
            accepted=response_model_matches(settings,observed_model)
            safe_model=observed_model if observed_model in (settings.chat_model,'gemini-3.8-flash-n') else 'UNVERIFIED'
            responses.append({'status':response.status_code,'model_matches_config':observed_model==settings.chat_model,
                'observed_model':safe_model,'route_version_matches_policy':accepted,
                'attempts':provider_budget(settings).counts()})
            Path('/tmp/sample-provider-responses.json').write_text(json.dumps(responses,ensure_ascii=False),encoding='utf-8')
            print('SAMPLE_PROVIDER '+json.dumps({'status':response.status_code,
                'model_matches_config':observed_model==settings.chat_model,'observed_model':safe_model,
                'route_version_matches_policy':accepted,
                'attempts':provider_budget(settings).counts()}),flush=True)
            if response.is_success and not accepted:
                from .provider_budget import BudgetError
                raise BudgetError('PROVIDER_RESPONSE_MODEL_MISMATCH')
        model.client._client.event_hooks['response'].append(response_metadata)
        async def async_response_metadata(response):
            await response.aread()
            response_metadata(response)
        model.aclient._client.event_hooks['response'].append(async_response_metadata)
        original=model.invoke
        def observed(variables,prompt_op,**kwargs):
            import json
            name=type(prompt_op).__name__
            print('SAMPLE_STAGE '+json.dumps({'stage':name,'state':'start','attempts':provider_budget(settings).counts()}),flush=True)
            try:
                result=original(variables,prompt_op,**kwargs)
            except Exception as exc:
                print('SAMPLE_STAGE '+json.dumps({'stage':name,'state':'error','type':type(exc).__name__,
                    'attempts':provider_budget(settings).counts()}),flush=True)
                raise
            print('SAMPLE_STAGE '+json.dumps({'stage':name,'state':'parsed','result_type':type(result).__name__,
                'executors':[getattr(task,'executor',None) if getattr(task,'executor',None) in ('Retriever','Deduce','Finish')
                             else 'UNVERIFIED' for task in result] if type(result) is list else None,
                'attempts':provider_budget(settings).counts()}),flush=True)
            return result
        model.invoke=observed
    return model


def make_runtime(settings: ApiSettings, release: ServingRelease, deadline: float) -> RequestRuntime:
    """Only the supervisor's authenticated, verified request may reach constructors."""
    ticket = _CURRENT.get()
    if ticket is None or (ticket[0] is not settings or ticket[1] is not release
                          or ticket[2].deadline != deadline):
        raise ApiFailure('NOT_READY')
    runtime = ticket[2]
    if runtime.capability not in ('query','retrieve'):
        raise ApiFailure('NOT_READY')
    runtime.budget.remaining()
    _unchanged(release)
    from kag.retriever.retriever import Retriever
    if settings.query_proof_sha256:
        from .sample_query import load_proof,cached_vector
        _,cache,_=load_proof(settings,release,capability=runtime.capability)
        fallback=None
        def embed(question):
            nonlocal fallback
            vector=cached_vector(cache,question)
            if vector is not None:return vector
            if fallback is None:fallback=_new_embedding(settings,runtime)
            return fallback(question)
    else:
        embed = _new_embedding(settings,runtime)
    runtime.budget.remaining()
    if runtime.capability=='query':
        from kag.legal_solver import build_pipeline
        llm = _new_llm(settings,runtime)
        runtime.budget.remaining()
    runtime.retriever = Retriever(runtime.reader,embed,_json(release.contract_bytes))
    if runtime.capability=='query':
        runtime.pipeline = build_pipeline(runtime.retriever,llm)
        if settings.query_proof_sha256:
            from .provider_budget import disable_instance_retries
            disable_instance_retries(runtime.pipeline,llm)
    return runtime


async def run_query(runtime: RequestRuntime, question: str, as_of):
    runtime.budget.remaining()
    if runtime.closed or question != runtime.question or as_of != runtime.as_of:
        raise ApiFailure('NOT_READY')
    from kag.legal_solver import aanswer
    try:
        result = await aanswer(question,pipeline=runtime.pipeline,as_of=as_of)
    except Exception as exc:
        import json,traceback
        frames=[dict(file=frame.filename.removeprefix('/workspace/'),line=frame.lineno,function=frame.name)
                for frame in traceback.extract_tb(exc.__traceback__)
                if frame.filename.startswith(('/workspace/kag/','/workspace/vendor/KAG/kag/'))]
        print('SAMPLE_QUERY_FAILURE '+json.dumps(dict(error_type=type(exc).__name__,frames=frames[-12:])),flush=True)
        runtime.budget.remaining()
        raise RuntimeFailure('PROVIDER_ERROR') from None
    runtime.budget.remaining()
    return result


async def run_retrieve(runtime: RequestRuntime, question: str, top_k=10, expand=False):
    runtime.budget.remaining()
    if runtime.closed or question != runtime.question:
        raise ApiFailure('NOT_READY')
    try:
        result = await asyncio.to_thread(runtime.retriever.retrieve,question,top_k=top_k,expand=expand)
    except Exception:
        runtime.budget.remaining()
        raise RuntimeFailure('PROVIDER_ERROR') from None
    runtime.budget.remaining()
    return result


class RuntimeSupervisor:
    """One process-owned slot; cancellation never cancels an in-flight Core task."""
    def __init__(self):
        self._task, self._budget = None, None
        self.closed = self.draining = False

    @property
    def busy(self):
        return self._task is not None

    @property
    def live_ready(self):
        return False

    def readiness(self):
        return {'runtime':'blocked','sources':'unknown','admission':'blocked' if self.busy or self.closed else 'pass'}

    async def sample_inspect(self, request, settings, release):
        authorize(request_principal(request),'inspect',None)
        deadline=time.monotonic()+REQUEST_SECONDS
        request.state.h1_deadline=deadline
        _require_configuration(settings,capability='retrieve-vector')
        if (type(release) is not ServingRelease or release.release_kind!='SAMPLE'
                or release.release_id!=settings.release_id or settings.secrets!=request.app.state.http_settings.secrets):
            raise ApiFailure('NOT_READY')
        if request.headers.getlist('x-kag-release-id')!=[release.release_id]:raise RuntimeFailure('RELEASE_MISMATCH')
        async def operation():
            reader=None
            try:
                _require_operational_proof(settings,release,capability='retrieve-vector')
                initialize_runtime()
                reader=await asyncio.to_thread(_new_reader,settings,release,self._budget)
                proof=await asyncio.to_thread(verify_sample_backend,release,settings.sample_proof_sha256,settings.reader_username,reader)
                from .inspection import sample_graph_view,dataset_readiness,provider_view
                value=await asyncio.to_thread(sample_graph_view,release,reader,proof)
                value['datasets']=await asyncio.to_thread(dataset_readiness,request.app.state.evaluation_root,release)
                value['providers']=provider_view(settings)
                await asyncio.to_thread(verify_sample_backend,release,settings.sample_proof_sha256,settings.reader_username,reader)
                _unchanged(release)
                return value
            finally:
                if reader is not None:(reader if callable(getattr(reader,'close',None)) else reader._opener).close()
        return await self.supervise(operation,deadline)

    async def sample_ready(self, request, settings, release, *, capability):
        deadline=time.monotonic()+REQUEST_SECONDS
        request.state.h1_deadline=deadline
        _require_configuration(settings,capability=capability)
        async def operation():
            reader=None
            try:
                proof,_,_=await asyncio.to_thread(_require_operational_proof,settings,release,capability=capability)
                initialize_runtime()
                reader=await asyncio.to_thread(_new_reader,settings,release,self._budget)
                await asyncio.to_thread(verify_sample_backend,release,settings.sample_proof_sha256,None,reader)
                from .sample_query import verify_gateway
                await asyncio.to_thread(verify_gateway,settings,proof)
                _unchanged(release)
                return {'status':'ready','capability':'query-v1' if capability=='query' else 'retrieve',
                    'checks':dict(auth='pass',runtime='pass',sources='pass',admission='pass'),
                    'release_kind':'SAMPLE','release_id':release.release_id,'provider_transport':'metadata_verified',
                    'production_write':'blocked'}
            finally:
                if reader is not None:
                    (reader if callable(getattr(reader,'close',None)) else reader._opener).close()
        return await self.supervise(operation,deadline)

    def _done(self, task):
        if not task.cancelled():
            task.exception()
        self._task = self._budget = None
        self.draining = False

    async def supervise(self, operation, deadline):
        if self.closed:
            raise ApiFailure('NOT_READY')
        if self.busy:
            raise RuntimeFailure('CONCURRENCY_LIMIT')
        budget = _Budget(deadline)
        budget.remaining()
        self._budget = budget

        async def run():
            try:
                return await operation()
            except (ApiFailure,RuntimeFailure):
                raise
            except Exception:
                raise ApiFailure('INTERNAL_ERROR') from None

        task = self._task = asyncio.create_task(run())
        task.add_done_callback(self._done)
        try:
            done, _ = await asyncio.wait({task},timeout=budget.remaining())
            if not done:
                budget.stop()
                self.draining = True
                raise ApiFailure('QUERY_TIMEOUT')
            budget.response_remaining()
            return task.result()
        except asyncio.CancelledError:
            budget.stop()
            self.draining = not task.done()
            raise

    async def query(self, request, settings, release, *, finalize=None, factory=None):
        # Entry precedes body consumption, so upload and every subsequent gate share 25s.
        deadline = time.monotonic()+(180.0 if settings.query_proof_sha256 else REQUEST_SECONDS)
        received_date = _today()
        request.state.h1_deadline = deadline
        parsed = await admit_request(request,'query')
        if request.query_params:
            raise ApiFailure('INVALID_REQUEST')
        if _today() != received_date:
            raise ApiFailure('DATE_BOUNDARY_CHANGED')
        try:
            _require_configuration(settings)
        except (ValueError,httpx.InvalidURL):
            raise ApiFailure('NOT_READY') from None

        async def operation():
            runtime = RequestRuntime(None,None,None,deadline,self._budget,parsed.message,None)
            runtime.request_id=getattr(request.state,'request_id',None)
            token = None
            meter_context = None
            try:
                as_of = await asyncio.to_thread(_identity,request,settings,release,parsed,received_date)
                runtime.as_of = as_of
                if settings.query_proof_sha256:runtime.budget.transport_seconds=60.0
                runtime.budget.remaining()
                _require_operational_proof(settings,release)
                initialize_runtime()
                from kag.interface.common.llm_client import LLMCallCcontext, TokenMeterFactory
                meter_context = LLMCallCcontext('h1-'+uuid4().hex,True)
                meter_context.__enter__()
                runtime.reader = await asyncio.to_thread(_new_reader,settings,release,runtime.budget)
                def preflight():
                    runtime.budget.remaining()
                    if settings.query_proof_sha256:
                        verify_sample_backend(release,settings.sample_proof_sha256,None,runtime.reader)
                        from .sample_query import load_proof,verify_gateway
                        proof,_,_=load_proof(settings,release)
                        verify_gateway(settings,proof)
                    _backend(runtime.reader,release)
                    _readback(runtime.reader,release.records,_json(release.contract_bytes))
                    _backend(runtime.reader,release)
                    _unchanged(release)
                    runtime.budget.remaining()
                await asyncio.to_thread(preflight)
                if _today() != as_of:
                    raise ApiFailure('DATE_BOUNDARY_CHANGED')
                token = _CURRENT.set((settings,release,runtime))
                runtime = await asyncio.to_thread(factory or make_runtime,settings,release,deadline)
                if _today() != as_of:
                    raise ApiFailure('DATE_BOUNDARY_CHANGED')
                result = await run_query(runtime,parsed.message,as_of)
                if settings.query_proof_sha256:
                    await asyncio.to_thread(verify_sample_backend,release,settings.sample_proof_sha256,None,runtime.reader)
                    from dataclasses import asdict
                    import json
                    Path('/tmp/sample-answer.json').write_text(json.dumps(asdict(result),ensure_ascii=False),encoding='utf-8')
                return result if finalize is None else await finalize(runtime,result,parsed)
            finally:
                if token is not None:
                    _CURRENT.reset(token)
                try:
                    try:
                        await runtime.close()
                    finally:
                        if meter_context is not None:
                            try:
                                TokenMeterFactory().remove_meter(meter_context.task_id)
                            finally:
                                meter_context.__exit__(None,None,None)
                except Exception:
                    self.closed = True
                    raise ApiFailure('INTERNAL_ERROR') from None

        return await self.supervise(operation,deadline)

    async def retrieve(self, request, settings, release, *, finalize=None, factory=None):
        deadline = time.monotonic()+REQUEST_SECONDS
        request.state.h1_deadline = deadline
        parsed = await admit_request(request,'inspect',RetrieveRequest)
        if request.query_params:
            raise ApiFailure('INVALID_REQUEST')
        try:
            _require_configuration(settings,capability='retrieve')
        except (ValueError,httpx.InvalidURL):
            raise ApiFailure('NOT_READY') from None

        async def operation():
            runtime = RequestRuntime(None,None,None,deadline,self._budget,parsed.message,None,
                                     capability='retrieve')
            runtime.request_id=getattr(request.state,'request_id',None)
            token = None
            try:
                await asyncio.to_thread(_identity,request,settings,release,parsed,capability='retrieve')
                runtime.budget.remaining()
                _require_operational_proof(settings,release,capability='retrieve')
                initialize_runtime()
                runtime.reader = await asyncio.to_thread(_new_reader,settings,release,runtime.budget)
                def integrity():
                    runtime.budget.remaining()
                    if settings.query_proof_sha256:
                        verify_sample_backend(release,settings.sample_proof_sha256,None,runtime.reader)
                    _backend(runtime.reader,release)
                    _readback(runtime.reader,release.records,_json(release.contract_bytes))
                    _backend(runtime.reader,release)
                    _unchanged(release)
                    runtime.budget.remaining()
                await asyncio.to_thread(integrity)
                token = _CURRENT.set((settings,release,runtime))
                runtime = await asyncio.to_thread(factory or make_runtime,settings,release,deadline)
                result = await run_retrieve(runtime,parsed.message,parsed.top_k,parsed.expand)
                await asyncio.to_thread(integrity)
                return result if finalize is None else await finalize(runtime,result,parsed)
            finally:
                if token is not None:
                    _CURRENT.reset(token)
                try:
                    await runtime.close()
                except Exception:
                    self.closed = True
                    raise ApiFailure('INTERNAL_ERROR') from None

        return await self.supervise(operation,deadline)

    async def sample_vector(self, request, settings, release, *, ready=False, finalize=None):
        deadline = time.monotonic()+REQUEST_SECONDS
        request.state.h1_deadline = deadline
        if ready:
            authorize(request_principal(request),'inspect',None)
        parsed = None if ready else await admit_request(request,'inspect',SampleVectorRequest)
        if not ready and request.query_params:
            raise ApiFailure('INVALID_REQUEST')
        _require_configuration(settings,capability='retrieve-vector')
        if settings.secrets != request.app.state.http_settings.secrets:
            raise ApiFailure('NOT_READY')

        async def operation():
            runtime = RequestRuntime(None,None,None,deadline,self._budget,'',None,capability='retrieve-vector')
            try:
                if ready:
                    if (type(release) is not ServingRelease or release.release_id != settings.release_id
                            or release.descriptor['source_snapshot_id'] != settings.source_snapshot_id
                            or request.headers.getlist('x-kag-release-id') != [settings.release_id]):
                        raise ApiFailure('NOT_READY')
                else:
                    _identity(request,settings,release,parsed,capability='retrieve-vector')
                _require_operational_proof(settings,release,capability='retrieve-vector')
                initialize_runtime()
                runtime.reader = await asyncio.to_thread(_new_reader,settings,release,runtime.budget)
                def integrity():
                    runtime.budget.response_remaining()
                    verify_sample_backend(release,settings.sample_proof_sha256,settings.reader_username,runtime.reader)
                    runtime.budget.response_remaining()
                await asyncio.to_thread(integrity)
                if ready:
                    result = {'status':'ready','capability':'retrieve-vector','release_kind':'SAMPLE',
                              'release_id':release.release_id,'provider_transport':'not_probed','production_write':'blocked'}
                else:
                    from kag.retriever.retriever import Retriever
                    vector = await asyncio.to_thread(sample_source_vector,release,runtime.reader,parsed.evidence_id)
                    runtime.retriever = Retriever(runtime.reader,None,_json(release.contract_bytes))
                    result = await asyncio.to_thread(runtime.retriever.retrieve_vector,vector,
                                                    top_k=parsed.top_k,expand=parsed.expand)
                    await asyncio.to_thread(integrity)
                return result if finalize is None else await finalize(runtime,result,parsed)
            finally:
                try:
                    await runtime.close()
                except Exception:
                    self.closed = True
                    raise ApiFailure('INTERNAL_ERROR') from None
        return await self.supervise(operation,deadline)

    async def close(self):
        self.closed = True
        if self._budget is not None:
            self._budget.stop()
        task = self._task
        if task is not None:
            try:
                await asyncio.shield(task)
            except (ApiFailure,RuntimeFailure):
                pass
            finally:
                if task.done() and self._task is task:
                    self._done(task)
