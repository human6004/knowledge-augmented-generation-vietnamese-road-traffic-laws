"""Portable Step8 entry point. H1 alone owns auth, admission and serving authority."""
from __future__ import annotations

from ipaddress import ip_address
import os
from pathlib import Path
import re


class ConfigurationError(RuntimeError):
    def __init__(self):
        super().__init__('KAG API startup configuration unavailable.')


def _policy():
    for key,value in {'KAG_OPERATIONAL_PROOF':'DENY','KAG_PRODUCTION_WRITE':'BLOCKED',
                      'KAG_PROVIDER_EGRESS':'DENY','KAG_DEBUG_DUMP_CONFIG':'0'}.items():
        if os.environ.get(key,value) != value:
            raise ConfigurationError()
    # Upstream init_env switches to remote project configuration when these are inherited.
    if any(key in os.environ for key in ('KAG_PROJECT_ID','KAG_PROJECT_HOST_ADDR')):
        raise ConfigurationError()


def _secret(key):
    path = os.environ.get(key)
    if not path:
        return None
    try:
        if not Path(path).is_absolute():
            raise ConfigurationError()
        with Path(path).open('rb') as stream:
            raw = stream.read(4099)
        if len(raw) > 4098:
            raise ConfigurationError()
        if raw.endswith(b'\r\n'):
            raw = raw[:-2]
        elif raw.endswith(b'\n'):
            raw = raw[:-1]
        if not 1 <= len(raw) <= 4096 or any(b in raw for b in (b'\0',b'\n',b'\r')):
            raise ConfigurationError()
        value = raw.decode('ascii',errors='strict')
        if not value.strip():
            raise ConfigurationError()
        return value
    except (OSError,UnicodeError,ValueError):
        raise ConfigurationError() from None


def server_options():
    _policy()
    host = os.environ.get('KAG_HTTP_HOST','0.0.0.0')
    port = os.environ.get('KAG_HTTP_PORT','8000')
    try:
        if (str(ip_address(host)) != host or not re.fullmatch(r'[0-9]{1,5}',port)
                or not 1 <= int(port) <= 65535 or os.environ.get('KAG_HTTP_WORKERS','1') != '1'):
            raise ConfigurationError()
    except ValueError:
        raise ConfigurationError() from None
    return host,int(port)


def create_app():
    """Uvicorn factory: local artifact reads only; never instantiate remote clients."""
    server_options()
    from .app import ApiSettings, create_app as h1_app
    from . import artifacts
    from .contract import ApiFailure
    from .runtime import RuntimeSettings
    try:
        for key in ('KAG_HTTP_QUERY_SECRET_FILE','KAG_HTTP_INSPECT_SECRET_FILE',
                    'KAG_HTTP_QUERY_PREVIOUS_SECRET_FILE','KAG_HTTP_INSPECT_PREVIOUS_SECRET_FILE'):
            if key in os.environ and not Path(os.environ[key]).is_absolute():
                raise ConfigurationError()
        settings = ApiSettings.from_env()
        if not (settings.secrets.query_tokens and settings.secrets.inspect_tokens):
            raise ConfigurationError()
        reader_user = os.environ.get('KAG_HTTP_READER_USERNAME') or None
        reader_password = _secret('KAG_HTTP_READER_PASSWORD_FILE')
        if ((reader_user is None) != (reader_password is None)
                or (reader_user is not None and (not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]{0,63}',reader_user)
                    or reader_user.lower() in ('root','admin','neo4j')))):
            raise ConfigurationError()
        provider_keys = {name:_secret('KAG_HTTP_'+name.upper()+'_KEY_FILE') for name in ('embedding','chat')}
        app = h1_app(settings,enable_sample_routes=True)
        release_id = os.environ.get('KAG_HTTP_RELEASE_ID')
        root = os.environ.get('KAG_HTTP_RELEASE_ROOT')
        if bool(release_id) != bool(root):
            raise ConfigurationError()
        if release_id:
            if not Path(root).is_absolute():
                raise ConfigurationError()
            release = artifacts.load_release(Path(root),release_id)
            source_id = os.environ.get('KAG_HTTP_SOURCE_SNAPSHOT_ID',release.descriptor['source_snapshot_id'])
            webapp_id = os.environ.get('KAG_HTTP_WEBAPP_SNAPSHOT_ID',release.descriptor['webapp_snapshot_id'])
            if source_id != release.descriptor['source_snapshot_id'] or webapp_id != release.descriptor['webapp_snapshot_id']:
                raise ConfigurationError()
            app.state.serving_release = release
            app.state.runtime_settings = RuntimeSettings(secrets=settings.secrets,release_id=release_id,
                source_snapshot_id=source_id,webapp_snapshot_id=webapp_id,
                reader_username=reader_user,reader_password=reader_password,
                embedding_url=os.environ.get('KAG_HTTP_EMBEDDING_URL') or None,
                embedding_model=os.environ.get('KAG_HTTP_EMBEDDING_MODEL') or None,embedding_key=provider_keys['embedding'],
                chat_url=os.environ.get('KAG_HTTP_CHAT_URL') or None,
                chat_model=os.environ.get('KAG_HTTP_CHAT_MODEL') or None,chat_key=provider_keys['chat'])
        return app
    except (ApiFailure,artifacts.ArtifactFailure,OSError,ValueError,TypeError):
        raise ConfigurationError() from None


def main():
    host,port = server_options()
    import uvicorn
    uvicorn.run('kag.http_api.server:create_app',factory=True,host=host,port=port,workers=1,
        proxy_headers=False,forwarded_allow_ips='',access_log=False,log_level='warning',
        lifespan='on',ws='none',limit_concurrency=16,timeout_keep_alive=5,
        timeout_graceful_shutdown=30,h11_max_incomplete_event_size=65536)


if __name__ == '__main__':
    main()
