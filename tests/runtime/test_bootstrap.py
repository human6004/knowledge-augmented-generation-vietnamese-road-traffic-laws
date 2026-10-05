"""Real pinned SDK import smoke; no SDK/model/service stubs."""
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]


class RuntimeImportTests(unittest.TestCase):
    def test_dirty_vendor_is_rejected_before_sdk_initialization(self):
        from kag import bootstrap
        real_run = subprocess.run
        def git_metadata(args, **kwargs):
            if args[0] != 'git':
                return real_run(args, **kwargs)
            output = (bootstrap.VENDOR_COMMIT if 'rev-parse' in args
                      else ' M kag/__init__.py\n?? kag/shadow.py\n')
            return subprocess.CompletedProcess(args, 0, output, '')
        with patch('kag.bootstrap.subprocess.run', side_effect=git_metadata):
            with self.assertRaisesRegex(RuntimeError, 'working tree'):
                bootstrap.initialize()

    def test_project_and_vendor_share_real_registry_without_network(self):
        self.assertTrue((ROOT / 'kag/bootstrap.py').is_file(),
                        'project-local KAG bootstrap is missing')
        code = r'''
import inspect
import importlib.metadata
from pathlib import Path
import sys

network_attempts = []
def deny_network(event, args):
    if event in ('socket.connect', 'socket.getaddrinfo'):
        network_attempts.append(event)
        raise AssertionError('runtime import must not access network')
sys.addaudithook(deny_network)

from kag.builder import codec
from kag.bootstrap import initialize
initialize()
from kag.common.conf import KAG_CONFIG
from kag.builder.writer_adapter import NativeIntegerKGWriter
from kag.builder.component.writer.kg_writer import KGWriter
from kag.builder.component.vectorizer.batch_vectorizer import BatchVectorizer
from kag.common.tools.search_api.impl.openspg_search_api import OpenSPGSearchAPI
from kag.common.tools.search_api.search_api_abc import SearchApiABC
from kag.interface import SinkWriterABC, VectorizerABC
from kag.builder.model.sub_graph import Node, SubGraph
import kag, knext

root = Path.cwd().resolve()
vendor = root / 'vendor/KAG'
for line in (root / 'requirements.txt').read_text().splitlines():
    if line and not line.startswith('#'):
        name, version = line.split('==')
        assert importlib.metadata.version(name) == version, f'dependency drift: {name}'
assert Path(inspect.getfile(codec)).is_relative_to(root / 'kag/builder')
assert Path(inspect.getfile(NativeIntegerKGWriter)).is_relative_to(root / 'kag/builder')
for cls in (KGWriter, BatchVectorizer, OpenSPGSearchAPI):
    assert Path(inspect.getfile(cls)).is_relative_to(vendor)
assert Path(knext.__file__).is_relative_to(vendor)
assert SinkWriterABC.by_name('kg_writer') is KGWriter
assert VectorizerABC.by_name('batch_vectorizer') is BatchVectorizer
assert SearchApiABC.by_name('openspg_search_api') is OpenSPGSearchAPI
assert issubclass(NativeIntegerKGWriter, KGWriter)
assert KAG_CONFIG._is_initialized
assert SubGraph([Node(_id='D0_2_OFFLINE', name='D0_2_OFFLINE',
                      label='LegalUnit', properties={'text': 'offline'})], []).nodes[0].id == 'D0_2_OFFLINE'
initialize()
assert SinkWriterABC.by_name('kg_writer') is KGWriter
assert not network_attempts
print('REAL_IMPORT_PASS; registry=PASS; network=0; embedding=0; graph_writes=0')
'''
        env = os.environ.copy()
        for name in ('PYTHONPATH', 'KAG_PROJECT_ID', 'KAG_PROJECT_HOST_ADDR'):
            env.pop(name, None)
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT,
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('REAL_IMPORT_PASS', result.stdout)


if __name__ == '__main__':
    unittest.main()
