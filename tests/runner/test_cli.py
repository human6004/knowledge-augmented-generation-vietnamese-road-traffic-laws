"""Official CLI glue plus a separate-process runner with network-only fixtures."""
import contextlib
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from kag.run_state import RunBlocked


ROOT = Path(__file__).resolve().parents[2]


class CliTests(unittest.TestCase):
    def api(self):
        self.assertTrue((ROOT / 'kag/__main__.py').is_file(), 'official CLI missing')
        return importlib.import_module('kag.__main__')

    def test_help_needs_no_sdk_or_network(self):
        self.api()
        process = subprocess.run([sys.executable, '-B', '-m', 'kag', '--help'], capture_output=True, text=True)
        self.assertEqual(process.returncode, 0)
        self.assertIn('resume', process.stdout)
        self.assertNotIn('matplotlib', process.stdout + process.stderr)
        with patch('kag.bootstrap.initialize', side_effect=AssertionError('help initialized SDK')):
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as error:
                self.api().main(['--help'])
        self.assertEqual(error.exception.code, 0)

    def test_three_commands_dispatch_same_library_config_and_identity(self):
        api = self.api()
        config = {'scope': 'test-dispatch'}
        for command in ('run', 'resume', 'verify'):
            with self.subTest(command=command), patch('kag.runner.load_config', return_value=config), \
                    patch('kag.runner.run', return_value=0) as run, \
                    patch('kag.runner.verify_run', return_value=0) as verify:
                self.assertEqual(api.main([command, '--config', '/outside/config.json', '--run-id', 'same-id']), 0)
                if command == 'verify': verify.assert_called_once_with(config, run_id='same-id')
                else: run.assert_called_once_with(config, run_id='same-id', resume=command == 'resume')

    def test_boundary_errors_are_fixed_messages_and_exact_exit_codes(self):
        api = self.api()
        for error, expected in ((RunBlocked('SCOPE'), 2), (TimeoutError('NEVER_LOG_SECRET_BODY'), 1)):
            output = io.StringIO()
            with patch('kag.runner.load_config', side_effect=error), contextlib.redirect_stderr(output):
                self.assertEqual(api.main(['run', '--config', '/outside/config.json', '--run-id', 'fixture']), expected)
            self.assertNotIn('NEVER_LOG_SECRET_BODY', output.getvalue())
            self.assertNotIn('Traceback', output.getvalue())

    def test_default_deny_subprocess_has_no_credential_dump(self):
        self.api()
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config.json'; config.write_text('{}')
            process = subprocess.run([sys.executable, '-B', '-m', 'kag', 'run', '--config', str(config),
                '--run-id', 'deny'], capture_output=True, text=True, env=dict(os.environ, KAG_EMBEDDING_KEY='NEVER_LOG_SECRET'))
        self.assertEqual(process.returncode, 2)
        self.assertNotIn('NEVER_LOG_SECRET', process.stdout + process.stderr)
        self.assertNotIn('Traceback', process.stdout + process.stderr)

    def test_process_cli_pass_error_blocked_and_status_match_library(self):
        self.api()
        script = '''
import json, os, sys
sys.path.insert(0, 'tests/runner')
from unittest.mock import patch
from test_runner import RunnerExecutionTests, checksum
from kag.builder.codec import canonical_json
from kag.__main__ import main
RunnerExecutionTests.setUpClass()
from knext.project import client as project
from kag import verify
case = RunnerExecutionTests(); case.setUp()
mode = sys.argv[1]
if mode == 'ERROR': case.reader.database_identity = lambda: (_ for _ in ()).throw(TimeoutError('RAW_SECRET'))
if mode == 'BLOCKED': case.config['input_sha256']['provenance'] = '0' * 64
path = case.root / 'config.json'; path.write_text(canonical_json(case.config), encoding='utf-8')
os.environ.update(TEST_NEO4J_USER='fixture', TEST_NEO4J_PASSWORD='SYNTHETIC_SECRET')
try:
    with patch.object(project, 'ProjectClient', return_value=case.projects), patch.object(verify, 'Neo4jReadClient', return_value=case.reader):
        code = main(['run', '--config', str(path), '--run-id', 'process-fixture'])
    print('CLI_RESULT=' + json.dumps({'exit': code, 'status': case.record('status.json', 'process-fixture')['state']}))
finally: case.doCleanups()
sys.exit(code)
'''
        for mode, code in (('PASS', 0), ('ERROR', 1), ('BLOCKED', 2)):
            with self.subTest(mode=mode):
                process = subprocess.run([sys.executable, '-B', '-c', script, mode], capture_output=True, text=True)
                self.assertEqual(process.returncode, code, process.stderr[-1000:])
                result = next(line.split('=', 1)[1] for line in process.stdout.splitlines() if line.startswith('CLI_RESULT='))
                self.assertEqual(json.loads(result), {'exit': code, 'status': mode})
                self.assertNotIn('RAW_SECRET', process.stdout + process.stderr)
                self.assertNotIn('SYNTHETIC_SECRET', process.stdout + process.stderr)


if __name__ == '__main__':
    unittest.main()
