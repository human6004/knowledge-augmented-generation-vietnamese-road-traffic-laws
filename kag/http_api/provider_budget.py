"""Persistent, provider-specific attempt limits for an authorized direct runner."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from types import MethodType

import httpx
import portalocker


class BudgetError(RuntimeError):
    """Fixed messages contain no credentials, request bodies or endpoints."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _object(pairs):
    value = {}
    for key,item in pairs:
        if key in value:
            raise ValueError('duplicate JSON key')
        value[key] = item
    return value


class ProviderBudget:
    CAP = 3

    def __init__(self, path, *, embedding_url, embedding_model, chat_url, chat_model, limits=None, in_place=False, development_only=False):
        self.path = Path(path).absolute()
        self.lock_path = self.path.with_name(self.path.name+'.lock')
        self.limits = {'embedding':self.CAP,'chat':self.CAP} if limits is None else dict(limits)
        if (type(development_only) is not bool or set(self.limits)!={'embedding','chat'}
                or (self.limits!={'embedding':None,'chat':None} if development_only else
                    any(type(n) is not int or not 1<=n<=maximum
                        for n,maximum in ((self.limits['embedding'],3),(self.limits['chat'],7))))
                or type(in_place) is not bool):
            raise BudgetError('PROVIDER_BINDING_INVALID')
        self.in_place = in_place
        self.providers = {}
        for kind, endpoint, model in (('embedding',embedding_url,embedding_model),
                                       ('chat',chat_url,chat_model)):
            try:
                url = httpx.URL(endpoint)
                suffix = '/embeddings' if kind=='embedding' else '/chat/completions'
                valid = (type(endpoint) is str and url.scheme in ('http','https')
                    and bool(url.host) and not url.userinfo and not url.query
                    and not url.fragment and url.path.endswith(suffix)
                    and type(model) is str and re.fullmatch(r'[A-Za-z0-9_./:-]{1,256}',model))
            except (TypeError,ValueError):
                valid = False
            if not valid:
                raise BudgetError('PROVIDER_BINDING_INVALID')
            self.providers[kind] = (url,model)
        binding = {k:[str(url),model] for k,(url,model) in self.providers.items()}
        self.binding = hashlib.sha256(json.dumps(binding,sort_keys=True,separators=(',',':')).encode()).hexdigest()

    @contextmanager
    def _locked(self):
        try:
            if self.path.is_symlink() or self.lock_path.is_symlink():
                raise BudgetError('ATTEMPT_LEDGER_UNAVAILABLE')
            with portalocker.Lock(str(self.lock_path),mode='a+',timeout=5) as lock:
                lock.seek(0)
                marker = lock.read()
                if marker and marker != self.binding+'\n':
                    raise BudgetError('ATTEMPT_LEDGER_INVALID')
                if not self.path.exists():
                    # A consumed ledger must never be silently recreated after deletion.
                    if marker:
                        raise BudgetError('ATTEMPT_LEDGER_UNAVAILABLE')
                    state = {'version':1,'binding_sha256':self.binding,
                             'attempts':{'embedding':0,'chat':0}}
                    self._write(state)
                else:
                    state = json.loads(self.path.read_text(encoding='utf-8'),object_pairs_hook=_object)
                if (type(state) is not dict or set(state)!={'version','binding_sha256','attempts'}
                        or type(state['version']) is not int or state['version']!=1
                        or state['binding_sha256']!=self.binding
                        or type(state['attempts']) is not dict
                        or set(state['attempts'])!={'embedding','chat'}
                        or any(type(n) is not int or n<0 or self.limits[k] is not None and n>self.limits[k]
                               for k,n in state['attempts'].items())):
                    raise BudgetError('ATTEMPT_LEDGER_INVALID')
                if not marker:
                    lock.write(self.binding+'\n')
                    lock.flush()
                    os.fsync(lock.fileno())
                yield state
        except BudgetError:
            raise
        except (OSError,ValueError,portalocker.exceptions.LockException):
            raise BudgetError('ATTEMPT_LEDGER_UNAVAILABLE') from None

    def _write(self, state):
        if self.in_place:
            # Exact bind-mounted files cannot be replaced. Crash-corrupted JSON denies all later sends.
            with self.path.open('r+',encoding='utf-8') as stream:
                stream.seek(0)
                json.dump(state,stream,sort_keys=True,separators=(',',':'))
                stream.truncate()
                stream.flush()
                os.fsync(stream.fileno())
            return
        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(prefix=self.path.name+'.',suffix='.tmp',dir=self.path.parent)
            with os.fdopen(fd,'w',encoding='utf-8') as stream:
                json.dump(state,stream,sort_keys=True,separators=(',',':'))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary,self.path)
            temporary = None
            if os.name=='posix':
                directory = os.open(self.path.parent,os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        finally:
            if temporary is not None:
                os.unlink(temporary)

    def counts(self):
        with self._locked() as state:
            return dict(state['attempts'])

    def reserve(self, kind):
        if kind not in self.providers:
            raise BudgetError('PROVIDER_BINDING_INVALID')
        with self._locked() as state:
            if self.limits[kind] is not None and state['attempts'][kind]>=self.limits[kind]:
                raise BudgetError('PROVIDER_ATTEMPT_BUDGET_EXHAUSTED')
            state['attempts'][kind]+=1
            self._write(state)
            return state['attempts'][kind]

    def _admit(self, kind, request):
        if kind not in self.providers:
            raise BudgetError('PROVIDER_BINDING_INVALID')
        url, model = self.providers[kind]
        try:
            body = json.loads(request.content,object_pairs_hook=_object)
            valid = (request.method=='POST' and request.url==url
                     and type(body) is dict and body.get('model')==model)
        except (ValueError,TypeError,httpx.RequestNotRead):
            valid = False
        if not valid:
            raise BudgetError('PROVIDER_REQUEST_DENIED')
        self.reserve(kind)

    def guard_sync(self, kind, transport):
        return _SyncTransport(self,kind,transport)

    def guard_async(self, kind, transport):
        return _AsyncTransport(self,kind,transport)

    def configure_sdk(self, model, kind):
        """Call before any SDK invocation; both clients and proxy mounts are guarded."""
        if kind not in self.providers:
            raise BudgetError('PROVIDER_BINDING_INVALID')
        for name, client_type, guard in (('client',httpx.Client,self.guard_sync),
                                         ('aclient',httpx.AsyncClient,self.guard_async)):
            sdk = getattr(model,name,None)
            client = getattr(sdk,'_client',None)
            if not isinstance(client,client_type):
                raise BudgetError('PROVIDER_BINDING_INVALID')
            sdk.max_retries = 0
            client.follow_redirects = False
            client._transport = guard(kind,client._transport)
            client._mounts = {pattern:guard(kind,transport) if transport else None
                              for pattern,transport in client._mounts.items()}


class _SyncTransport(httpx.BaseTransport):
    def __init__(self, budget, kind, transport):
        self.budget,self.kind,self.transport = budget,kind,transport

    def handle_request(self, request):
        self.budget._admit(self.kind,request)
        response = self.transport.handle_request(request)
        if 300<=response.status_code<400:
            response.close()
            raise BudgetError('PROVIDER_REDIRECT_DENIED')
        return response

    def close(self):
        self.transport.close()


class _AsyncTransport(httpx.AsyncBaseTransport):
    def __init__(self, budget, kind, transport):
        self.budget,self.kind,self.transport = budget,kind,transport

    async def handle_async_request(self, request):
        self.budget._admit(self.kind,request)
        response = await self.transport.handle_async_request(request)
        if 300<=response.status_code<400:
            await response.aclose()
            raise BudgetError('PROVIDER_REDIRECT_DENIED')
        return response

    async def aclose(self):
        await self.transport.aclose()


def disable_instance_retries(pipeline, llm):
    """Unwrap only this request's methods; preserve upstream classes and five iterations."""
    methods = [(pipeline,'planning'),(llm,'call_with_json_parse'),(llm,'acall_with_json_parse')]
    if getattr(pipeline,'max_iteration',None)!=5:
        raise BudgetError('PIPELINE_BINDING_INVALID')
    unwrapped = []
    for instance,name in methods:
        original = getattr(type(instance),name,None)
        function = getattr(original,'__wrapped__',None)
        if not callable(function):
            raise BudgetError('PIPELINE_BINDING_INVALID')
        unwrapped.append((instance,name,function))
    for instance,name,function in unwrapped:
        setattr(instance,name,MethodType(function,instance))
