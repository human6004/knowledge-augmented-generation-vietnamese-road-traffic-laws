"""One private control thread around the existing Runner; GraphLock owns graph exclusion."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from kag.builder.production_scope import ProductionSettings, _spec_hash, validate_c3_manifest
from kag.http_api.contract import ApiFailure
from kag.http_api.security import ServiceSecrets, authenticate, bounded_body
from kag.run_state import MESSAGES, RunBlocked, _shared_lock_root, validate_run_directory
from kag.runner import _config, _files, run


def _input_version(path):
    value=Path(path).stat()
    return value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_ctime_ns


def inspect_inputs(value):
    """Read configured inputs only; full Runner preflight remains authoritative."""
    result = dict(contract_version='builder-inputs-v1', configuration='NOT_CONFIGURED',
                  error_code=None, scope=None, target=None, inputs=[], preflight='NOT_RUN',
                  source_validation=dict(state='NOT_RUN',error_code=None,plan_sha256=None,nodes=None,edges=None))
    if value is None:
        return result
    try:
        config = _config(value)
        if config['scope'] not in ('FRESH_SAMPLE', 'PRODUCTION'):
            raise RunBlocked('SCOPE')
    except (ValueError, KeyError, TypeError):
        result.update(configuration='INVALID', error_code='CONFIG')
        return result
    result.update(configuration='CONFIGURED', scope=config['scope'],
                  target={key: config[key] for key in ('project_id', 'database', 'namespace')})
    for name, digest in config['input_sha256'].items():
        try:
            if not Path(config['paths'][name]).is_file():
                state = 'MISSING'
            else:
                state = 'NOT_CHECKED'
        except (OSError, ValueError):
            state = 'UNAVAILABLE'
        result['inputs'].append(dict(name=name, sha256=digest, state=state))
    return result


def check_source_inputs(value):
    config = _config(value)
    contract = json.loads((Path(__file__).resolve().parents[1]/'schema/schema_contract.json').read_bytes())
    data = validate_c3_manifest(contract, config['paths']['c3_manifest'])
    try:
        _files(dict(config,input_sha256={'c3_manifest':config['input_sha256']['c3_manifest']}))
        result = dict(state='VALID',error_code=None,plan_sha256=data['manifest']['plan_sha256'],
                      nodes=len(data['nodes']),edges=len(data['edges']))
        # shortcut: UI cache assumes file metadata changes; recheck after metadata-preserving restores.
        checks = tuple((path,_input_version(path)) for path,_ in data['file_checksums'] if path!=data['index'].path)
        return result,checks
    finally:
        data['index'].close()


class BuilderControl:
    def __init__(self, config, *, runner=run):
        self.config = _config(config)
        if self.config['write_mode'] != 'WRITE':
            raise RunBlocked('SCOPE')
        if self.config['scope'] == 'PRODUCTION':
            config=self.config
            try:
                ProductionSettings(scope=config['scope'],runtime_location=config['runtime_location'],
                    host_addr=config['endpoints']['openspg'],neo4j_uri=config['endpoints']['neo4j_uri'],
                    project_name=config['project_name'],namespace=config['namespace'],expected_project_id=config['project_id'],
                    vector_dimensions=config['vector_dimensions'],confirmation=config['confirmation']).validate()
            except ValueError:
                raise RunBlocked('SCOPE') from None
        elif (self.config['scope'] != 'FRESH_SAMPLE' or self.config['vector_policy'] != 'replay-existing'
                or not (re.fullmatch(r'freshsample[a-z0-9]{8,40}', self.config['database'])
                        or self.config['runtime_location'] == 'container' and self.config['database'] == 'vietroadtraffic')):
            raise RunBlocked('SCOPE')
        if self.config['scope'] == 'FRESH_SAMPLE' and self.config['runtime_location'] == 'container':
            from kag.backend_identity import BackendIdentityError, _isolated_builder_password
            try: _isolated_builder_password()
            except (BackendIdentityError, OSError): raise RunBlocked('SCOPE') from None
        self.runner = runner
        self.thread = None
        self.stop_event = threading.Event()
        self.run_id = None
        self.failed = False
        self.result = None
        self.previous_status = None
        # Protect the local HTTP/thread state only; this is not another database writer lock.
        self._monitor = threading.RLock()
        root = Path(self.config['paths']['run_root'])
        if root.exists():
            records = [(self._record(path.name), path.name) for path in root.iterdir()]
            if records:
                self.run_id = max(records, key=lambda row: row[0][0]['updated_at'])[1]
                self.failed = any(uncertain or not (
                    status['state'] == 'PASS' and status['stage'] == 'release'
                    or status['state'] == 'ERROR' and status['error_code'] == 'INTERRUPTED')
                    for (status, uncertain), _ in records)

    def _directory(self, run_id):
        return validate_run_directory(self.config['paths']['run_root'], run_id,
            read_only_paths=[path for name, path in self.config['paths'].items()
                             if path and name not in ('run_root', 'lock_root')])

    def _record(self, run_id):
        ledger = self._directory(run_id) / 'ledger.sqlite3'
        if ledger.is_symlink() or not ledger.is_file():
            raise RunBlocked('INTEGRITY')
        try:
            with closing(sqlite3.connect(ledger.as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
                db.execute('BEGIN')
                meta = dict(db.execute("SELECT key,value FROM run_meta WHERE key IN ('identity','status')"))
                identity, status = json.loads(meta['identity']), json.loads(meta['status'])
                pending = db.execute("SELECT 1 FROM run_batches WHERE state='INTENT' "
                    "AND stage IN ('write-nodes','write-edges') LIMIT 1").fetchone() is not None
            if (identity['config_hash'] != _spec_hash(self.config) or identity['run_id'] != run_id
                    or identity['database'] != self.config['database']
                    or not isinstance(identity['database_id'], str) or not identity['database_id']
                    or status['run_id'] != run_id or status['error_code'] not in (None, *MESSAGES)
                    or type(status['done']) is not int or type(status['total']) is not int
                    or not 0 <= status['done'] <= status['total']
                    or not isinstance(status['updated_at'], str)):
                raise ValueError
            lock = Path(self.config['paths']['lock_root']) / (
                hashlib.sha256(identity['database_id'].encode()).hexdigest() + '.lock')
            return status, pending or lock.exists() or lock.is_symlink()
        except (OSError, sqlite3.Error, ValueError, KeyError, TypeError):
            raise RunBlocked('INTEGRITY') from None

    def status(self):
        with self._monitor:
            alive = self.thread is not None and self.thread.is_alive()
            state, progress, code = 'IDLE', None, None
            if alive:
                state = 'STOPPING' if self.stop_event.is_set() else 'RUNNING'
                try:
                    durable, _ = self._record(self.run_id)
                    progress = {key: durable[key] for key in ('stage', 'done', 'total')}
                except RunBlocked:
                    pass  # Preflight has not created its verified ledger yet.
            else:
                try:
                    _shared_lock_root(self.config['paths']['lock_root'])
                    if self.failed:
                        raise RunBlocked('INTEGRITY')
                    if self.run_id is not None:
                        durable, uncertain = self._record(self.run_id)
                        progress = {key: durable[key] for key in ('stage', 'done', 'total')}
                        code = durable['error_code']
                        if self.result is not None and durable == self.previous_status:
                            raise RunBlocked('SCOPE' if self.result == 2 else 'RUNTIME')
                        if uncertain:
                            raise RunBlocked(code or 'LOCK')
                        if self.result == 2:
                            state, code = 'BLOCKED', code or 'SCOPE'
                        elif durable['state'] == 'ERROR' and code == 'INTERRUPTED':
                            state = 'STOPPED'
                        elif durable['state'] == 'PASS' and durable['stage'] == 'release':
                            state = 'COMPLETE'
                        else:
                            state = 'BLOCKED'
                            code = code or 'INTEGRITY'
                except RunBlocked as error:
                    state, code = 'BLOCKED', error.code
            return dict(contract_version='builder-control-v1', state=state, run_id=self.run_id,
                target={key: self.config[key] for key in ('project_id', 'database', 'namespace')},
                progress=progress, error_code=code,
                actions=dict(build=state in ('IDLE', 'COMPLETE'), stop=state == 'RUNNING',
                             resume=state == 'STOPPED', delete=False),
                delete_reason='DELETE_NOT_AUTHORIZED',
                production_write='CONFIGURED' if self.config['scope']=='PRODUCTION' else 'BLOCKED')

    def start(self, run_id, *, resume=False):
        with self._monitor:
            directory = self._directory(run_id)
            current = self.status()
            if (not current['actions']['resume' if resume else 'build']
                    or resume and run_id != self.run_id or not resume and directory.exists()):
                raise HTTPException(409, 'BUILDER_CONFLICT')
            self.run_id, self.failed = run_id, False
            self.result = None
            self.previous_status = self._record(run_id)[0] if resume else None
            self.stop_event = threading.Event()
            def execute():
                try:
                    self.result = self.runner(self.config, run_id=run_id, resume=resume, stop_event=self.stop_event)
                    if self.result not in (0, 1, 2):
                        self.failed = True
                except BaseException:
                    self.failed = True
            self.thread = threading.Thread(target=execute, name='kag-builder', daemon=False)
            self.thread.start()
            return self.status()

    def stop(self, run_id):
        with self._monitor:
            if (run_id != self.run_id or self.thread is None or not self.thread.is_alive()
                    or self.stop_event.is_set()):
                raise HTTPException(409, 'BUILDER_CONFLICT')
            self.stop_event.set()
            return self.status()

    def close(self):
        with self._monitor:
            self.stop_event.set()
            thread = self.thread
        if thread is not None:
            thread.join()  # Drain Runner; never cancel a remote write or delete its lock.


def create_app(*, control=None, token=None):
    if token is None:
        token = Path(os.environ['KAG_BUILDER_TOKEN_FILE']).read_text(encoding='utf-8').strip()
    # Reuse bearer validation; this app knows only its independent control secret.
    secrets = ServiceSecrets(inspect_tokens=(token,))
    failure = None
    configuration = control.config if control is not None else None
    if control is None:
        try:
            configuration = json.loads(Path(os.environ['KAG_BUILDER_CONFIG']).read_bytes())
        except (FileNotFoundError, KeyError):
            failure = 'CONFIG'
        except (OSError, ValueError):
            configuration, failure = {}, 'CONFIG'
        else:
            try:
                control = BuilderControl(configuration)
            except (OSError, KeyError, ValueError):
                failure = 'CONFIG'

    source_result=inspect_inputs(None)['source_validation']
    checked_files=()
    checked_config=None
    source_task=None

    @asynccontextmanager
    async def lifespan(app):
        yield
        if source_task is not None:
            await source_task
        if control is not None:
            await asyncio.to_thread(control.close)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(ApiFailure)
    async def denied(request, error):
        return JSONResponse({'error': {'code': error.code}}, status_code=error.status)

    def authenticate_request(request):
        headers = request.headers.getlist('authorization')
        if len(headers) > 1:
            raise ApiFailure('AUTH_INVALID')
        authenticate(headers[0] if headers else None, secrets)
        if request.query_params:
            raise ApiFailure('INVALID_REQUEST')

    @app.get('/v1/builder/inputs')
    async def inputs(request: Request):
        nonlocal source_result,checked_files
        authenticate_request(request)
        result=await asyncio.to_thread(inspect_inputs, configuration)
        if source_result['state']!='CHECKING':
            if checked_config is not None and checked_config!=_spec_hash(configuration):
                source_result=inspect_inputs(None)['source_validation']
                checked_files=()
            elif checked_files:
                try:
                    if await asyncio.to_thread(lambda:any(_input_version(path)!=version for path,version in checked_files)):
                        raise ValueError
                except (OSError,ValueError):
                    source_result=dict(state='INVALID',error_code='INTEGRITY',plan_sha256=None,nodes=None,edges=None)
                    checked_files=()
        result['source_validation']=source_result
        if source_result['state']=='VALID':
            for row in result['inputs']:
                if row['name']=='c3_manifest':row['state']='MATCHED'
        return result

    @app.post('/v1/builder/inputs',status_code=202)
    async def check_inputs(request: Request):
        nonlocal source_task,source_result,checked_files,checked_config
        authenticate_request(request)
        try:
            if json.loads(await bounded_body(request))!={}:
                raise ValueError
        except (ValueError,TypeError):
            raise ApiFailure('INVALID_REQUEST') from None
        result=await asyncio.to_thread(inspect_inputs,configuration)
        if (source_task is not None and not source_task.done() or result['configuration']!='CONFIGURED'
                or not any(row['name']=='c3_manifest' and row['state']=='NOT_CHECKED' for row in result['inputs'])):
            raise HTTPException(409,'SOURCE_CHECK_BLOCKED')
        checked_files=()
        checked_config=_spec_hash(configuration)
        source_result=dict(state='CHECKING',error_code=None,plan_sha256=None,nodes=None,edges=None)
        async def check():
            nonlocal source_result,checked_files
            try:
                source_result,checked_files=await asyncio.to_thread(check_source_inputs,configuration)
            except ValueError:
                source_result=dict(state='INVALID',error_code='INTEGRITY',plan_sha256=None,nodes=None,edges=None)
            except Exception:
                source_result=dict(state='UNAVAILABLE',error_code='RUNTIME',plan_sha256=None,nodes=None,edges=None)
        source_task=asyncio.create_task(check())
        result['source_validation']=source_result
        return result

    @app.get('/v1/builder/status')
    async def status(request: Request):
        authenticate_request(request)
        if control is None:
            return dict(contract_version='builder-control-v1', state='BLOCKED', run_id=None,
                target=None, progress=None, error_code=failure,
                actions=dict(build=False, stop=False, resume=False, delete=False),
                delete_reason='DELETE_NOT_AUTHORIZED', production_write='BLOCKED')
        return await asyncio.to_thread(control.status)

    @app.post('/v1/builder/{action}', status_code=202)
    async def action(action: str, request: Request):
        authenticate_request(request)
        if action == 'delete':
            raise HTTPException(409, 'DELETE_NOT_AUTHORIZED')
        if action not in ('build', 'stop', 'resume'):
            raise HTTPException(404, 'UNKNOWN_ACTION')
        try:
            body = json.loads(await bounded_body(request))
            if not isinstance(body, dict) or set(body) != {'run_id'}:
                raise ValueError
            if control is None:
                raise HTTPException(409, 'BUILDER_BLOCKED')
            control._directory(body['run_id'])
        except (ValueError, TypeError):
            raise ApiFailure('INVALID_REQUEST') from None
        if action == 'stop':
            return await asyncio.to_thread(control.stop, body['run_id'])
        return await asyncio.to_thread(control.start, body['run_id'], resume=action == 'resume')

    return app


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('kag.builder.control:create_app', factory=True, host='0.0.0.0', port=8010,
                workers=1, limit_concurrency=16, access_log=False)
