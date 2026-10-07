import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from fixtures import module, record
from test_legacy import legacy


class CLITests(unittest.TestCase):
    def cli(self,*args):
        script = """import runpy,sys
def deny(event,args):
    if event in ('socket.connect','socket.getaddrinfo'): raise AssertionError('network')
sys.addaudithook(deny)
try: runpy.run_module('kag.evaluation',run_name='__main__')
finally:
    assert 'kag.legal_solver' not in sys.modules
    assert 'kag.common.conf' not in sys.modules
"""
        return subprocess.run([sys.executable,'-B','-c',script,*map(str,args)],capture_output=True)

    def test_validate_freeze_cli_offline(self):
        module('__main__')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=root/'data.jsonl'
            source.write_text(json.dumps(record()),encoding='utf-8')
            self.assertEqual(self.cli('validate',source).returncode,0)
            result=self.cli('freeze',source,'--output-root',root/'freeze','--dataset-version','synthetic-frozen')
            self.assertEqual(result.returncode,0,result.stderr.decode())
            frozen=list((root/'freeze').rglob('eval_questions.jsonl'))[0]
            self.assertEqual(self.cli('validate',frozen).returncode,0)
            source.write_bytes(b'bad')
            self.assertEqual(self.cli('validate',source).returncode,2)
            self.assertEqual(self.cli('validate',root/'absent').returncode,1)

    def test_import_cli_limit_no_overwrite_no_live_official_routes(self):
        module('__main__')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=root/'legacy.json'
            source.write_text(json.dumps([legacy(id=str(i)) for i in range(4)]),encoding='utf-8')
            args=('import-legacy',source,'--output-dir',root/'import','--dataset-version','p','--limit','3')
            result=self.cli(*args)
            self.assertEqual(result.returncode,2,result.stderr.decode())
            report=json.loads((root/'import'/'import_report.json').read_bytes())
            self.assertEqual(report['counts'],{'converted':0,'needs_manual_mapping':3,'rejected':0,'requested':3})
            self.assertFalse((root/'import'/'eval_questions.jsonl').exists())
            before=(root/'import'/'import_report.json').read_bytes()
            self.assertEqual(self.cli(*args).returncode,1)
            self.assertEqual((root/'import'/'import_report.json').read_bytes(),before)
            for args in (('g1',),('g2',),('freeze',source,'--official'),('import-legacy',source,'--limit','0')):
                self.assertEqual(self.cli(*args).returncode,2)


if __name__ == '__main__':
    unittest.main()
