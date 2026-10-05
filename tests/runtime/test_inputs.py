"""Versioned external inputs must preserve the approved C1-C4 byte hashes."""
import hashlib
import json
from pathlib import Path
import unittest

from kag.builder.inputs import ARTIFACT_HASHES


ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / 'artifacts/inputs/xref-a3g2'


class VersionedInputTests(unittest.TestCase):
    def test_canonical_inputs_match_existing_builder_pins(self):
        self.assertTrue((INPUTS / 'manifest.json').is_file(),
                        'versioned external input manifest is missing')
        manifest = json.loads((INPUTS / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual({r['name']: r['sha256'] for r in manifest['files']},
                         dict(ARTIFACT_HASHES))
        for name, expected in ARTIFACT_HASHES:
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256((INPUTS / name).read_bytes()).hexdigest(),
                                 expected)


if __name__ == '__main__':
    unittest.main()
