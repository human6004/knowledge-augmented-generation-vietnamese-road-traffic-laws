"""Offline vector entry; no question embedding or provider."""
import unittest
from test_retriever import CONTRACT, VECTOR, ReadFixture
from kag.retriever.retriever import Retriever


class VectorEntryTests(unittest.TestCase):
    def test_supplied_vector_reuses_four_targets_without_embedding(self):
        self.assertTrue(callable(getattr(Retriever,'retrieve_vector',None)), 'vector entry missing')
        reader = ReadFixture()
        retriever = Retriever(reader, None, CONTRACT)
        self.assertEqual(retriever.retrieve_vector(VECTOR), [])
        self.assertEqual(len(reader.calls), 4)
        with self.assertRaises(ValueError):
            retriever.retrieve('No provider authorized')

    def test_invalid_vector_and_boolean_limits_denied_before_reads(self):
        self.assertTrue(callable(getattr(Retriever,'retrieve_vector',None)), 'vector entry missing')
        reader = ReadFixture()
        retriever = Retriever(reader, None, CONTRACT)
        for vector in ([], [0.0]*3072, [float('nan')]+[0.0]*3071):
            with self.assertRaises(ValueError):
                retriever.retrieve_vector(vector)
        with self.assertRaises(ValueError):
            retriever.retrieve_vector(VECTOR, top_k=True)
        self.assertEqual(reader.calls, [])
