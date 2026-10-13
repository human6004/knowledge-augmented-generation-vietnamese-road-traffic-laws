"""Initialize the pinned SDK beside project modules, once per process.

Call initialize() before importing SDK components. Ordinary offline builder
imports stay lightweight and do not initialize the SDK.
"""
import importlib
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'vendor/KAG'
VENDOR_COMMIT = 'fdab15b3929d2ee40dfcdd388f90233096a6afc9'
_initialized = False


def initialize():
    global _initialized
    if _initialized:
        return
    expected_python = (ROOT / '.python-version').read_text(encoding='ascii').strip()
    if '.'.join(map(str, sys.version_info[:3])) != expected_python:
        raise RuntimeError(f'KAG runtime requires Python {expected_python}')
    if not (VENDOR / 'kag/__init__.py').is_file():
        raise RuntimeError('Initialize the pinned vendor/KAG submodule first')
    result = subprocess.run(
        ['git', '-c', f'safe.directory={VENDOR}', '-C', str(VENDOR), 'rev-parse', 'HEAD'],
        capture_output=True, text=True, check=False,
    )
    if result.returncode or result.stdout.strip() != VENDOR_COMMIT:
        raise RuntimeError('vendor/KAG commit differs from the runtime pin')
    result = subprocess.run(
        ['git', '-c', f'safe.directory={VENDOR}', '-C', str(VENDOR),
         '-c', 'core.autocrlf=true', '-c', 'core.filemode=false',
         'status', '--porcelain', '--untracked-files=all'],
        capture_output=True, text=True, check=False,
    )
    if result.returncode or result.stdout.strip():
        raise RuntimeError('vendor/KAG working tree differs from the runtime pin')
    for name in ('knext', 'kag.common', 'kag.interface'):
        module = sys.modules.get(name)
        if module is not None and not Path(module.__file__).resolve().is_relative_to(VENDOR):
            raise RuntimeError('Call kag.bootstrap.initialize before importing an installed SDK')

    import kag
    import kag.builder
    sys.path.insert(0, str(VENDOR))
    kag.__path__.insert(0, str(VENDOR / 'kag'))
    kag.builder.__path__.append(str(VENDOR / 'kag/builder'))
    solver = sys.modules.get('kag.solver')
    if solver is not None and Path(solver.__file__).resolve() != ROOT / 'kag/solver/__init__.py':
        solver = None
    os.environ['KAG_DEBUG_DUMP_CONFIG'] = '0'
    if solver is not None:
        # Resolve the upstream initializer while retaining preloaded package references.
        importlib.reload(solver)
    # Execute the upstream entry point with the shared package namespace;
    # its real component registrations and init_env remain authoritative.
    entry = VENDOR / 'kag/__init__.py'
    exec(compile(entry.read_bytes(), str(entry), 'exec'), vars(kag))
    _initialized = True


if __name__ == '__main__':
    initialize()
    print('KAG_BOOTSTRAP_PASS')
