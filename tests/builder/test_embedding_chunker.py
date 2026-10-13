"""Exact offsets, bounded splitting, and overlap-aware pooling contracts."""
import hashlib
import importlib.util
import math
from pathlib import Path
import sys
import unittest


PATH = Path(__file__).resolve().parents[2] / 'kag/builder/embedding_chunker.py'


class EmbeddingChunkerTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(PATH.exists(), 'deterministic embedding chunker missing')
        spec = importlib.util.spec_from_file_location('kag.builder.embedding_chunker', PATH)
        self.code = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.code
        spec.loader.exec_module(self.code)

    def test_paragraph_boundary_precedes_line_and_sentence(self):
        text = 'abcde\n\nf. gh\nijklmnop'
        chunks = self.code.chunk_text(text, 14, 0)
        self.assertEqual(chunks[0], (0, 7))

    def test_line_boundary_when_no_paragraph(self):
        self.assertEqual(self.code.chunk_text('abcdef\nghijklmnop', 12, 0)[0], (0, 7))

    def test_sentence_boundary_when_no_line(self):
        self.assertEqual(self.code.chunk_text('abcdef; ghijklmnop', 12, 0)[0], (0, 8))

    def test_hard_boundary_only_when_natural_unavailable(self):
        self.assertEqual(self.code.chunk_text('abcdefghijklmnop', 8, 0), [(0, 8), (8, 16)])

    def test_overlap_exact_offsets_and_complete_coverage(self):
        text = 'abcdefghijklmnopqr'
        offsets = self.code.chunk_text(text, 8, 2)
        self.assertEqual(offsets, [(0, 8), (6, 14), (12, 18)])
        self.assertEqual(self.code.effective_weights(offsets, len(text)), [8, 6, 4])
        self.assertEqual(''.join(text[fresh:end] for (_,end),fresh in zip(offsets, [0,8,14])), text)

    def test_overlap_prefers_natural_start_within_limit(self):
        text = 'abcd\nef\nghijklmnop'
        offsets = self.code.chunk_text(text, 10, 6)
        self.assertEqual(offsets[:2], [(0, 8), (5, 15)])
        self.assertTrue(all(b-a <= 10 for a,b in offsets))

    def test_no_empty_chunks_and_unicode_offsets_are_exact(self):
        text = 'Luật 🚦\n\nĐiều đ\nquy định Việt'
        offsets = self.code.chunk_text(text, 12, 2)
        self.assertTrue(all(text[a:b].strip() for a,b in offsets))
        self.assertEqual(sum(self.code.effective_weights(offsets, len(text))), len(text))
        self.assertEqual(text.encode(), 'Luật 🚦\n\nĐiều đ\nquy định Việt'.encode())

    def test_whitespace_only_is_explicitly_unembeddable(self):
        with self.assertRaises(ValueError): self.code.chunk_text(' \n\t', 8, 2)

    def test_invalid_overlap_rejected(self):
        for maximum, overlap in [(0,0), (8,8), (8,-1), (True,0)]:
            with self.subTest(maximum=maximum, overlap=overlap), self.assertRaises(ValueError):
                self.code.chunk_text('abcdef', maximum, overlap)

    def test_adaptive_split_near_half_with_natural_boundary(self):
        self.assertEqual(self.code.split_chunk('abcdefgh\nijklmnop', (0,17), 4), [(0,9),(9,17)])

    def test_adaptive_split_stops_when_children_would_be_below_minimum(self):
        self.assertIsNone(self.code.split_chunk('abcdef', (0,6), 4))

    def test_weighted_pooling_and_l2_math(self):
        vector = self.code.pool_vectors([[1.0,0.0], [0.0,1.0]], [3,4], 2)
        self.assertAlmostEqual(vector[0], 0.6)
        self.assertAlmostEqual(vector[1], 0.8)
        self.assertAlmostEqual(math.hypot(*vector), 1.0)

    def test_overlap_does_not_receive_duplicate_weight(self):
        weights = self.code.effective_weights([(0,8),(6,14),(12,18)], 18)
        vector = self.code.pool_vectors([[1.,0.],[0.,1.],[0.,1.]], weights, 2)
        self.assertAlmostEqual(vector[0], 8 / math.hypot(8,10))
        self.assertAlmostEqual(vector[1], 10 / math.hypot(8,10))

    def test_coverage_gap_or_unordered_chunk_cannot_pool(self):
        for offsets in [[(0,4),(5,8)], [(0,4),(4,6),(2,8)], [(1,8)], [(0,7)]]:
            with self.subTest(offsets=offsets), self.assertRaises(ValueError):
                self.code.effective_weights(offsets, 8)

    def test_adaptive_child_fully_inside_overlap_gets_zero_weight(self):
        weights=self.code.effective_weights([(0,8),(2,6),(4,12),(6,10),(6,14),(8,16)],16)
        self.assertEqual(weights,[8,0,4,0,2,2])
        vector=self.code.pool_vectors([[1.,0.],[0.,1.]], [8,0], 2)
        self.assertEqual(vector,[1.,0.])

    def test_invalid_or_cancelling_vectors_never_make_fake_aggregate(self):
        for vectors in [[[0.,0.]], [[float('nan'),1.]], [[1.]], [[1.,0.],[-1.,0.]]]:
            with self.subTest(vectors=vectors), self.assertRaises(ValueError):
                self.code.pool_vectors(vectors, [1]*len(vectors), 2)

    def test_large_finite_vectors_normalize_without_overflow(self):
        vector = self.code.pool_vectors([[1e308,1e308]], [8000], 2)
        self.assertTrue(all(math.isfinite(v) for v in vector))
        self.assertAlmostEqual(math.hypot(*vector),1.0)

    def test_zero_weight_large_vector_cannot_underflow_weighted_source(self):
        self.assertEqual(self.code.pool_vectors([[1e-100,0.],[1e308,1e308]],[1,0],2),[1.,0.])


if __name__ == '__main__': unittest.main()
