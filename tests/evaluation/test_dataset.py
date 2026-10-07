import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fixtures import module, record


class DatasetTests(unittest.TestCase):
    def test_direct_protocol_constructor_matches_factory_hash(self):
        d,m = module('dataset'),module('models')
        direct=m.EvaluationProtocol(ks=(3,1),top_k=3)
        factory=m.EvaluationProtocol.from_dict({'ks':[1,3],'top_k':3})
        self.assertEqual(direct.ks,(1,3))
        self.assertEqual(d.canonical_protocol_bytes(direct),d.canonical_protocol_bytes(factory))
        self.assertEqual(direct.protocol_hash,factory.protocol_hash)
        raw={'name':'mock','temperature':1}
        direct=m.EvaluationProtocol(ks=(3,1),top_k=3,judge_config=raw)
        factory=m.EvaluationProtocol.from_dict({'ks':[1,3],'top_k':3,'judge_config':raw})
        self.assertEqual(d.canonical_protocol_bytes(direct),d.canonical_protocol_bytes(factory))
        self.assertIs(type(direct.to_dict()['judge_config']['temperature']),float)
        before=direct.protocol_hash
        raw['name']='mutated'
        self.assertEqual(direct.protocol_hash,before)

    def test_freeze_stable_hash_and_changed_gold(self):
        d = module('dataset')
        self.assertTrue(hasattr(d,'freeze_dataset'),'freeze feature missing')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'source.jsonl'
            original = d.canonical_line(record(gold_unit_ids=['u']))
            source.write_bytes(original)
            a = d.freeze_dataset(source,root/'a','frozen-v1')
            b = d.freeze_dataset(source,root/'b','frozen-v1')
            adata = a.with_name('eval_questions.jsonl')
            bdata = b.with_name('eval_questions.jsonl')
            self.assertEqual(adata.read_bytes(),bdata.read_bytes())
            ds = d.load_dataset(adata)
            manifest = json.loads(a.read_bytes())
            self.assertEqual(ds.dataset_hash,manifest['sha256'])
            self.assertEqual(ds.canonical_bytes,adata.read_bytes())
            self.assertTrue(ds.manifest_verified)
            self.assertFalse(ds.official_benchmark)
            self.assertEqual(manifest['source_sha256'],hashlib.sha256(original).hexdigest())
            self.assertEqual(manifest['category_counts'],{'definition':1})
            self.assertEqual(source.read_bytes(),original)
            source.write_bytes(d.canonical_line(record(gold_unit_ids=['v'])))
            changed = d.freeze_dataset(source,root/'a','frozen-v2')
            self.assertNotEqual(json.loads(changed.read_bytes())['sha256'],ds.dataset_hash)

    def test_freeze_no_overwrite_and_manifest_tampering(self):
        d, m = module('dataset'), module('models')
        self.assertTrue(hasattr(d,'freeze_dataset'),'freeze feature missing')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root/'s.jsonl'
            source.write_bytes(d.canonical_line(record()))
            manifest_path = d.freeze_dataset(source,root,'frozen-v1')
            data_path = manifest_path.with_name('eval_questions.jsonl')
            original = data_path.read_bytes()
            with self.assertRaises(FileExistsError):
                d.freeze_dataset(source,root,'frozen-v1')
            with self.assertRaises(m.ValidationError):
                d.freeze_dataset(data_path,root,'frozen-v2')
            with self.assertRaises(m.ValidationError):
                d.freeze_dataset(source,root,'synthetic')
            empty = root/('dataset-'+hashlib.sha256(b'empty').hexdigest())
            empty.mkdir()
            with self.assertRaises(FileExistsError):
                d.freeze_dataset(source,root,'empty')
            manifest = json.loads(manifest_path.read_bytes())
            for key,value in (('sha256','0'*64),('record_count',2),('record_count',True),('category_counts',{}),
                              ('dataset_version','changed'),('schema_version','2'),('dataset_status','PROVISIONAL'),
                              ('frozen_at','2026-01-01'),('official_benchmark',1),('extra','x')):
                with self.subTest(key=key),self.assertRaises(m.ValidationError):
                    d.verify_frozen(original,dict(manifest,**{key:value}))
            with self.assertRaises(m.ValidationError):
                d.verify_frozen(original.replace(b'\n',b'\r\n'),manifest)
            manifest_path.unlink()
            with self.assertRaises(m.ValidationError):
                d.load_dataset(data_path)

    def test_freeze_publish_failure_is_not_frozen(self):
        d, m = module('dataset'), module('models')
        self.assertTrue(hasattr(d,'freeze_dataset'),'freeze feature missing')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root/'s.jsonl'
            raw = d.canonical_line(record())
            source.write_bytes(raw)
            real_open = Path.open
            def broken(path,*args,**kwargs):
                if path.name == 'eval_questions.manifest.json':
                    raise OSError('synthetic failure')
                return real_open(path,*args,**kwargs)
            with patch.object(Path,'open',broken),self.assertRaises(OSError):
                d.freeze_dataset(source,root,'failed-v1')
            data = root/('dataset-'+hashlib.sha256(b'failed-v1').hexdigest())/'eval_questions.jsonl'
            self.assertTrue(data.exists())
            with self.assertRaises(m.ValidationError):
                d.load_dataset(data)
            with self.assertRaises(FileExistsError):
                d.freeze_dataset(source,root,'failed-v1')
            self.assertEqual(source.read_bytes(),raw)

    def test_canonical_line_utf8_lf(self):
        d = module('dataset')
        self.assertEqual(d.canonical_line({'z':1, 'a':'Đường\n'}),
                         b'{"a":"\xc4\x90\xc6\xb0\xe1\xbb\x9dng\\n","z":1}\n')

    def test_canonical_hash_matches_exact_bytes(self):
        d, m = module('dataset'), module('models')
        a, b = record(qid='á'), record(qid='z')
        ds = d.dataset_from_records([a,b])
        expected = b''.join(d.canonical_line(r.to_dict()) for r in reversed(ds.records))
        self.assertEqual(ds.canonical_bytes, expected)
        self.assertEqual(ds.dataset_hash, hashlib.sha256(expected).hexdigest())
        self.assertEqual(ds.dataset_hash, d.dataset_from_records([b,a]).dataset_hash)
        self.assertIsNone(ds.source_sha256)
        for change in ({'question':'đổi'}, {'gold_unit_ids':['u']}, {'dataset_version':'v2'}, {'dataset_status':'FROZEN'}):
            changed = d.dataset_from_records([record(**change)])
            self.assertNotEqual(changed.dataset_hash, d.dataset_from_records([record()]).dataset_hash)
        self.assertNotEqual(d.dataset_from_records([record(question='é')]).dataset_hash,
                            d.dataset_from_records([record(question='e\u0301')]).dataset_hash)
        p = m.EvaluationProtocol.from_dict({'ks':[3,1], 'top_k':3})
        self.assertEqual(d.canonical_protocol_bytes(p), d.canonical_protocol_bytes(m.EvaluationProtocol.from_dict({'ks':[1,3], 'top_k':3})))
        for config in ({'ks':[1],'top_k':3}, {'ks':[1,3],'top_k':4}, {'ks':[1,3],'top_k':3,'judge_config':{'name':'mock'}}):
            self.assertNotEqual(d.canonical_protocol_bytes(p), d.canonical_protocol_bytes(m.EvaluationProtocol.from_dict(config)))

    def test_strict_loader_errors(self):
        d, m = module('dataset'), module('models')
        invalid = [record(qid=' q'), record(qid='q\x01'), record(category='other'), record(as_of='2026-02-30'),
                   record(expected_abstain=1), record(question=' '), record(foo=1), record(gold_unit_ids=['u','u']),
                   record(answer_reference={'foo':'x'}), record(citation_gold=[{'doc_id':'d','unit_id':'u','field':'text','start':True,'end':2,'quote':'x'}]),
                   record(citation_gold=[{'doc_id':'d','field':'text','start':0,'end':1,'quote':'x'}]),
                   record(legacy_references=[{'document_id':'d','text':'x','required':'true'}])]
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(m.ValidationError):
                d.dataset_from_records([item])
        for items in ([], [record(),record()], [record(),record(qid='q2',dataset_version='other')],
                      [record(),record(qid='q2',dataset_status='FROZEN')], [dict(record(),schema_version='2')]):
            with self.assertRaises(m.ValidationError):
                d.dataset_from_records(items)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'data.jsonl'
            for raw in (b'{', b'{"qid":"q","qid":"x"}', b'[]', b'{"x":NaN}', b'\xff', b'\xef\xbb\xbf{}'):
                path.write_bytes(b'\n'+raw+b'\n')
                issues = d.validate_dataset(path)
                self.assertTrue(issues)
                self.assertEqual(issues[0].path, str(path))
                self.assertEqual(issues[0].line, 2 if raw not in (b'\xff',b'\xef\xbb\xbf{}') else 1)
                self.assertTrue(issues[0].code)
        for config in ({'ks':[True]}, {'ks':[1,1]}, {'top_k':0}, {'expand':True}, {'api_key':'secret'},
                       {'judge_config':{'name':'x','temperature':float('nan')}}, {'judge_config':{'name':'x','secret':'x'}}):
            with self.assertRaises(m.ValidationError):
                m.EvaluationProtocol.from_dict(config)

    def test_jsonl_blank_lines_and_vietnamese_preserved(self):
        d = module('dataset')
        item = record(question='  Đường\nviệt e\u0301  ', gold_unit_ids=['Điều-1'])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'data.jsonl'
            raw = b'\n'+json.dumps(item,ensure_ascii=False).encode()+b'\r\n\n'
            path.write_bytes(raw)
            ds = d.load_dataset(path)
            self.assertEqual(ds.records[0].question,item['question'])
            self.assertEqual(ds.source_sha256,hashlib.sha256(raw).hexdigest())
            self.assertNotIn(b'\r',ds.canonical_bytes)

    def test_gold_shapes_and_deep_immutable_record(self):
        d = module('dataset')
        payload = record(gold_unit_ids=['u'],citation_gold=[{'doc_id':'d','unit_id':'u'}],
                         answer_reference={'markers':['30,5%']})
        ds = d.dataset_from_records([payload])
        before = ds.records[0].to_dict()
        payload['gold_unit_ids'].append('v')
        payload['citation_gold'][0]['doc_id']='changed'
        payload['answer_reference']['markers'].append('other')
        self.assertEqual(ds.records[0].to_dict(),before)
        self.assertEqual(before['citation_gold'][0]['required'],True)
        self.assertIsNone(before['citation_gold'][0]['field'])
        for fields in ({}, {'gold_doc_ids':['d','e']}, {'expected_abstain':True},
                       {'gold_sign_ids':['s'],'citation_gold':[{'doc_id':'d','sign_id':'s','unit_id':'anchor','field':'moTa','start':0,'end':1,'quote':'Đ'}]}):
            self.assertEqual(len(d.dataset_from_records([record(**fields)]).records),1)


if __name__ == '__main__':
    unittest.main()
