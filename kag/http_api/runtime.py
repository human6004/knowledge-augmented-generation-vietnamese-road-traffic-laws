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
                        _backend, _json, _readback, _unchanged)
from .contract import ApiFailure
from .security import admit_request

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


class _Budget:
    def __init__(self, deadline, clock=time.monotonic):
        if type(deadline) not in (float,int) or not math.isfinite(deadline):
            raise ApiFailure('NOT_READY')
        self.deadline, self.clock = deadline, clock
        self.stopped = threading.Event()
        self.finished = False

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
    remaining = min(TRANSPORT_SECONDS,budget.remaining())
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


def _require_configuration(settings):
    if type(settings) is not RuntimeSettings:
        raise ApiFailure('NOT_READY')
    for name in RuntimeSettings.__dataclass_fields__:
        if name != 'secrets':
            value = getattr(settings,name)
            if type(value) is not str or not value.strip() or len(value) > 4096:
                raise ApiFailure('NOT_READY')
    for name in ('embedding_key','chat_key','reader_password'):
        if getattr(settings,name).lower() in ('dummy','abc123'):
            raise ApiFailure('NOT_READY')
    for name in ('embedding_url','chat_url'):
        url = httpx.URL(getattr(settings,name))
        if url.scheme not in ('http','https') or not url.host or url.userinfo or url.query or url.fragment:
            raise ApiFailure('NOT_READY')


def _require_operational_proof(settings, release):
    # shortcut: no independent operational attestation available; authorize it separately before live serving.
    raise ArtifactFailure(VerificationState.UNVERIFIED)


def _identity(request, settings, release, parsed, as_of=None):
    if type(release) is not ServingRelease:
        raise ApiFailure('NOT_READY')
    if parsed.schema_contract != release.schema_contract:
        raise RuntimeFailure('SCHEMA_CONTRACT_MISMATCH')
    if release.release_id != settings.release_id:
        raise RuntimeFailure('RELEASE_MISMATCH')
    if release.descriptor['source_snapshot_id'] != settings.source_snapshot_id:
        raise RuntimeFailure('SOURCE_SNAPSHOT_MISMATCH')
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


def _new_embedding(settings, runtime):
    from kag.common.vectorize_model.openai_model import OpenAIVectorizeModel
    model = _sdk_instance(OpenAIVectorizeModel,runtime,model=settings.embedding_model,
        api_key=settings.embedding_key,base_url=settings.embedding_url,
        vector_dimensions=3072,timeout=TRANSPORT_SECONDS)
    return model.vectorize


def _new_llm(settings, runtime):
    from kag.common.llm.openai_client import OpenAIClient
    return _sdk_instance(OpenAIClient,runtime,name='h1-'+uuid4().hex,model=settings.chat_model,
        api_key=settings.chat_key,base_url=settings.chat_url,enable_check=False,timeout=TRANSPORT_SECONDS)


def make_runtime(settings: ApiSettings, release: ServingRelease, deadline: float) -> RequestRuntime:
    """Only the supervisor's authenticated, verified request may reach constructors."""
    ticket = _CURRENT.get()
    if ticket is None or (ticket[0] is not settings or ticket[1] is not release
                          or ticket[2].deadline != deadline):
        raise ApiFailure('NOT_READY')
    runtime = ticket[2]
    runtime.budget.remaining()
    _unchanged(release)
    from kag.retriever.retriever import Retriever
    from kag.legal_solver import build_pipeline
    embed = _new_embedding(settings,runtime)
    runtime.budget.remaining()
    llm = _new_llm(settings,runtime)
    runtime.budget.remaining()
    runtime.retriever = Retriever(runtime.reader,embed,_json(release.contract_bytes))
    runtime.pipeline = build_pipeline(runtime.retriever,llm)
    return runtime


async def run_query(runtime: RequestRuntime, question: str, as_of):
    runtime.budget.remaining()
    if runtime.closed or question != runtime.question or as_of != runtime.as_of:
        raise ApiFailure('NOT_READY')
    from kag.legal_solver import aanswer
    try:
        result = await aanswer(question,pipeline=runtime.pipeline,as_of=as_of)
    except Exception:
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
        deadline = time.monotonic()+REQUEST_SECONDS
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
            token = None
            meter_context = None
            try:
                as_of = await asyncio.to_thread(_identity,request,settings,release,parsed,received_date)
                runtime.as_of = as_of
                runtime.budget.remaining()
                _require_operational_proof(settings,release)
                initialize_runtime()
                from kag.interface.common.llm_client import LLMCallCcontext, TokenMeterFactory
                meter_context = LLMCallCcontext('h1-'+uuid4().hex,True)
                meter_context.__enter__()
                runtime.reader = await asyncio.to_thread(_new_reader,settings,release,runtime.budget)
                def preflight():
                    runtime.budget.remaining()
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
