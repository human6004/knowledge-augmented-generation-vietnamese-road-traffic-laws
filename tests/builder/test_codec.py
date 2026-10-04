"""Synthetic tests of the C1/C1.1 property boundary; no SDK startup."""
import copy
import importlib
import importlib.util
import json
from pathlib import Path
import unittest


CONTRACT = json.loads((Path(__file__).resolve().parents[2] /
                       'kag/schema/schema_contract.json').read_text(encoding='utf-8'))


def property_row(name, kind='TEXT', required=False, physical=None):
    return dict(logical_name=name, schema_name=physical or name,
                contract_type=kind, required=required)


class CodecTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('kag.builder.codec'),
                             'C2 codec implementation missing')
        self.codec = importlib.import_module('kag.builder.codec')

    def test_canonical_unicode_dict_order_and_list_order(self):
        value = {'z': ['đường', 'á'], 'a': {'y': 0, 'b': 'Việt Nam'}}
        before = copy.deepcopy(value)
        expected = '{"a":{"b":"Việt Nam","y":0},"z":["đường","á"]}'
        self.assertEqual(self.codec.canonical_json(value), expected)
        self.assertEqual(self.codec.canonical_json(dict(reversed(list(value.items())))), expected)
        self.assertEqual(value, before)

    def test_optional_omit_missing_and_none_preserve_empty_zero_false(self):
        rows = [property_row('a', 'OPTIONAL_TEXT'), property_row('b', 'OPTIONAL_TEXT'),
                property_row('empty', 'OPTIONAL_TEXT'), property_row('zero', 'OPTIONAL_INTEGER'),
                property_row('flag', 'BOOLEAN_ENCODING'), property_row('json', 'JSON_TEXT')]
        self.assertEqual(self.codec.encode_properties(
            {'a': None, 'empty': '', 'zero': 0, 'flag': False, 'json': None}, rows),
            {'empty': '', 'zero': 0, 'flag': 'false'})

    def test_integer_native_zero_seven_and_large(self):
        for kind in ('INTEGER', 'OPTIONAL_INTEGER'):
            for value in (0, 7, 2**63):
                with self.subTest(kind=kind, value=value):
                    got = self.codec.encode_properties({'n': value}, [property_row('n', kind)])['n']
                    self.assertIs(type(got), int)
                    self.assertEqual(got, value)

    def test_integer_rejects_bool_text_and_float(self):
        for kind in ('INTEGER', 'OPTIONAL_INTEGER'):
            for value in (True, False, '7', 7.0):
                with self.subTest(kind=kind, value=value):
                    with self.assertRaisesRegex(self.codec.BuilderContractError, 'n.*int'):
                        self.codec.encode_properties({'n': value}, [property_row('n', kind)])

    def test_boolean_lowercase_exact(self):
        for value, expected in ((True, 'true'), (False, 'false')):
            self.assertEqual(self.codec.encode_properties(
                {'b': value}, [property_row('b', 'BOOLEAN_ENCODING')]), {'b': expected})

    def test_boolean_rejects_non_boolean(self):
        for value in (0, 1, 'true', 'false'):
            with self.subTest(value=value):
                with self.assertRaisesRegex(self.codec.BuilderContractError, 'b.*bool'):
                    self.codec.encode_properties({'b': value}, [property_row('b', 'BOOLEAN_ENCODING')])

    def test_text_preserves_exact_unicode_and_empty(self):
        rows = [property_row('x', physical='physicalX')]
        for value in ('', '  Đường e\u0301  ', '7', 'null'):
            self.assertEqual(self.codec.encode_properties({'x': value}, rows), {'physicalX': value})
        for value in (7, False, [], {}):
            with self.assertRaisesRegex(self.codec.BuilderContractError, 'x.*str'):
                self.codec.encode_properties({'x': value}, rows)

    def test_json_text_encodes_logical_object_once(self):
        rows = [property_row('value', 'JSON_TEXT', physical='jsonValue')]
        value = {'b': ['Việt', 'Nam'], 'a': None}
        raw = self.codec.encode_properties({'value': value}, rows)
        self.assertEqual(raw['jsonValue'], '{"a":null,"b":["Việt","Nam"]}')
        self.assertEqual(self.codec.decode_properties(raw, rows), {'value': value})

    def test_json_text_string_is_logical_string_without_heuristic(self):
        rows = [property_row('j', 'JSON_TEXT')]
        logical = '["đường"]'
        encoded = self.codec.encode_properties({'j': logical}, rows)
        self.assertEqual(json.loads(encoded['j']), logical)
        self.assertEqual(self.codec.decode_properties(encoded, rows), {'j': logical})

    def test_decode_explicit_server_outer_layer(self):
        rows = [property_row('id', required=True), property_row('text'),
                property_row('n', 'INTEGER'), property_row('b', 'BOOLEAN_ENCODING'),
                property_row('j', 'JSON_TEXT')]
        raw = {'id': '7', 'text': '"đường"', 'n': '7', 'b': '"false"',
               'j': '"[\"đường\"]"'}
        # Construct the exact server representation without hand-escaped JSON.
        raw['j'] = json.dumps('["đường"]', ensure_ascii=False)
        self.assertEqual(self.codec.decode_properties(raw, rows, server_encoded=True),
                         {'id': '7', 'text': 'đường', 'n': 7, 'b': 'false', 'j': ['đường']})

    def test_decode_rejects_numeric_text_as_integer(self):
        rows = [property_row('n', 'INTEGER')]
        for raw, outer in (({'n': '7'}, False), ({'n': '"7"'}, True),
                           ({'n': 'true'}, True), ({'n': '7.0'}, True)):
            with self.subTest(raw=raw, outer=outer):
                with self.assertRaisesRegex(self.codec.BuilderContractError, 'n.*int'):
                    self.codec.decode_properties(raw, rows, server_encoded=outer)

    def test_decode_boolean_is_physical_text_and_invalid_rejected(self):
        rows = [property_row('b', 'BOOLEAN_ENCODING')]
        self.assertEqual(self.codec.decode_properties({'b': 'false'}, rows), {'b': 'false'})
        for value in (True, 0, 'False'):
            with self.assertRaisesRegex(self.codec.BuilderContractError, 'b'):
                self.codec.decode_properties({'b': value}, rows)

    def test_decode_malformed_json_rejected_with_property(self):
        for outer in (True, False):
            with self.assertRaisesRegex(self.codec.BuilderContractError, 'j.*JSON'):
                self.codec.decode_properties({'j': '{bad'}, [property_row('j', 'JSON_TEXT')],
                                             server_encoded=outer)

    def test_required_missing_null_and_blank_identity_rejected(self):
        for name in ('id', 'name'):
            rows = [property_row(name, required=True)]
            for values in ({}, {name: None}, {name: ''}, {name: ' \t\n'}):
                with self.subTest(name=name, values=values):
                    with self.assertRaisesRegex(self.codec.BuilderContractError, name):
                        self.codec.validate_properties(values, rows, CONTRACT['unit_type_values'])
        with self.assertRaisesRegex(self.codec.BuilderContractError, 'text.*required'):
            self.codec.encode_properties({}, [property_row('text', required=True)])

    def test_required_text_empty_valid_and_requirement_from_schema(self):
        self.assertEqual(self.codec.encode_properties({'text': ''},
                         [property_row('text', required=True)]), {'text': ''})
        with self.assertRaisesRegex(self.codec.BuilderContractError, 'so_hieu.*required'):
            self.codec.validate_properties({'id': 'D', 'name': 'D'},
                         CONTRACT['node_properties']['LegalDocument'], CONTRACT['unit_type_values'])

    def test_unit_type_enum_exact(self):
        rows = [property_row('unit_type', physical='unitType')]
        for value in CONTRACT['unit_type_values']:
            self.codec.validate_properties({'unit_type': value}, rows, CONTRACT['unit_type_values'])
        for value in ('dieu', ' Dieu', 'Dieu ', 'Other', ''):
            with self.subTest(value=value):
                with self.assertRaisesRegex(self.codec.BuilderContractError, 'unit_type.*enum'):
                    self.codec.validate_properties({'unit_type': value}, rows, CONTRACT['unit_type_values'])

    def test_invalid_contract_type_rejected(self):
        with self.assertRaisesRegex(self.codec.BuilderContractError, 'contract type'):
            self.codec.encode_properties({'x': 7}, [property_row('x', 'FLOAT')])


if __name__ == '__main__':
    unittest.main()
