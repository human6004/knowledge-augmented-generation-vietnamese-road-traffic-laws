"""Shared validation and lightweight imports must survive contract extraction."""
import importlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]


class VectorContractTests(unittest.TestCase):
    def contract(self):
        self.assertIsNotNone(importlib.util.find_spec('kag.vector_contract'),
                             'shared vector contract missing')
        return importlib.import_module('kag.vector_contract')

    def test_vector_validation_preserves_finite_nonzero_list_semantics(self):
        contract = self.contract()
        self.assertEqual(contract.TARGETS, {
            'LegalDocument': (('title', '_title_vector'),),
            'LegalUnit': (('text', '_text_vector'),),
            'TrafficSign': (('ten', '_ten_vector'), ('moTa', '_mo_ta_vector'))})
        for vector, dimension, expected in (
                ([1, 0.0, -2], 3, True), ([1.0] + [0.0] * 3071, 3072, True),
                ([0, -0.0], 2, False), ([], 0, False), ([1], 3072, False),
                ((1, 2), 2, False), (None, 1, False), ([True], 1, False),
                (['1'], 1, False), ([float('nan')], 1, False),
                ([float('inf')], 1, False), ([-float('inf')], 1, False)):
            with self.subTest(vector=vector, dimension=dimension):
                self.assertIs(contract.valid_vector(vector, dimension), expected)
        with self.assertRaises(OverflowError):
            contract.valid_vector([10 ** 400], 1)

    def test_legacy_imports_share_contract_objects(self):
        contract = self.contract()
        legacy = importlib.import_module('kag.builder.resilient_vectorizer')
        self.assertIs(legacy.TARGETS, contract.TARGETS)
        self.assertIs(legacy._valid_vector, contract.valid_vector)
        self.assertEqual(legacy.ResilientVectorizer.__module__, 'kag.builder.resilient_vectorizer')

    def test_read_and_scope_imports_do_not_load_embedding_or_sdk(self):
        code = '''
import importlib, importlib.util, sys
assert importlib.util.find_spec('kag.vector_contract') is not None, 'shared vector contract missing'
importlib.import_module(sys.argv[1])
assert 'kag.builder.resilient_vectorizer' not in sys.modules
assert 'kag.interface' not in sys.modules
assert 'knext' not in sys.modules
from kag.bootstrap import initialize
assert not sys.modules['kag.bootstrap']._initialized
'''
        for name in ('kag.vector_contract', 'kag.retriever.retriever',
                     'kag.verify', 'kag.builder.production_scope', 'kag.runner'):
            with self.subTest(module=name):
                result = subprocess.run([sys.executable, '-B', '-c', code, name], cwd=ROOT,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
