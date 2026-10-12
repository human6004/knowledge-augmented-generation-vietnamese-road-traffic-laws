import copy
import json
from pathlib import Path
import tempfile
import unittest
from fixtures import module


def sources():
    text = 'Nguồn synthetic: không phạt 30.000 đồng; đọc é 🚦.'
    record = dict(entity_type='VietRoadTraffic.LegalUnit',entity_id='d::u',doc_id='d',unit_id='d::u',sign_id=None,
                  field='text',source_text=text,source_sha256=module('dataset').sha256(text.encode()),metadata={'dieu_number':'1'})
    return dict(schema='h1-source-catalog-1.0',graph_fingerprint='a'*64,source_snapshot_id='test-source',records=[record])

def config():
    return dict(dataset_version='generated-synthetic',as_of='2026-10-12',categories=['definition','multi_hop','unanswerable'])

def draft(**changes):
    value = dict(qid='q1',question='Theo nguồn synthetic, nội dung gì?',category='definition',expected_abstain=False,
        expected_behavior='EXTRACT_ONLY',focus='nội dung',rationale='Đọc đúng nguồn; không khẳng định hiệu lực.',
        evidence=[dict(entity_type='VietRoadTraffic.LegalUnit',entity_id='d::u',field='text',start=0,end=len(sources()['records'][0]['source_text']),required=True)])
    value.update(changes)
    return value


class GenerationTests(unittest.TestCase):
    def test_real_catalog_traffic_sign_field_alias_maps_to_native_citation(self):
        catalog=sources();sign=copy.deepcopy(catalog['records'][0]);sign.update(entity_type='VietRoadTraffic.TrafficSign',entity_id='s',unit_id=None,sign_id='s',field='mo_ta',physical_field='moTa')
        catalog['records'].append(sign)
        result=self.generate(catalog)
        self.assertEqual(len(result['records']),1)
        d=draft();d['evidence'][0].update(entity_type=sign['entity_type'],entity_id='s',field='moTa')
        self.assertEqual(self.generate(catalog,[d])['records'][0]['citation_gold'][0]['field'],'moTa')

    def generate(self,catalog=None,drafts=None,settings=None):
        return module('generation').generate_questions(catalog or sources(),drafts or [draft()],settings or config())

    def test_source_first_provisional_exact_unicode_and_reproducible(self):
        result=self.generate();record=result['records'][0]
        self.assertEqual(record['dataset_status'],'PROVISIONAL')
        self.assertEqual(record['citation_gold'][0]['quote'],sources()['records'][0]['source_text'])
        self.assertEqual(record['gold_unit_ids'],['d::u'])
        self.assertEqual(record['answer_reference']['accepted_facts'],[sources()['records'][0]['source_text']])
        self.assertEqual(result,self.generate())
        notes=json.loads(record['notes']);self.assertFalse(notes['human_reviewed'])
        self.assertEqual(notes['review_status'],'PROVISIONAL');self.assertEqual(notes['applicability'],'NOT_VERIFIED')
        ds=module('dataset').dataset_from_records(result['records'])
        module('generation').validate_generated(ds,sources(),result['manifest'])
        self.assertEqual(result['manifest']['category_counts']['definition'],1)
        self.assertFalse(result['manifest']['official_benchmark'])

    def test_catalog_hash_tamper_ambiguous_source_or_identity_rejected(self):
        for change in ('hash','duplicate','identity','field'):
            catalog=sources()
            if change=='hash':catalog['records'][0]['source_text']+='tampered'
            elif change=='duplicate':catalog['records'].append(copy.deepcopy(catalog['records'][0]))
            elif change=='identity':catalog['records'][0]['unit_id']='different'
            else:catalog['records'][0]['field']='title'
            with self.subTest(change=change),self.assertRaises(module('models').ValidationError):self.generate(catalog)

    def test_invalid_span_bool_and_untrusted_gold_rejected(self):
        for changes in ({'start':True},{'end':100000},{'start':1,'end':0},{'quote':'fabricated'}):
            d=draft();d['evidence'][0].update(changes)
            with self.subTest(changes=changes),self.assertRaises(module('models').ValidationError):self.generate(drafts=[d])
        d=draft();d['answer_reference']={'expected_answer':'LLM gold'}
        with self.assertRaises(module('models').ValidationError):self.generate(drafts=[d])

    def test_missing_source_deferred_not_fake_eligible(self):
        d=draft();d['evidence'][0]['entity_id']='absent'
        result=self.generate(drafts=[d]);self.assertEqual(result['records'],[])
        self.assertEqual(result['manifest']['deferred'][0]['reason'],'SOURCE_NOT_AVAILABLE')
        self.assertEqual(result['manifest']['category_counts']['definition'],0)

    def test_multihop_independent_articles_and_rationale(self):
        catalog=sources();other=copy.deepcopy(catalog['records'][0]);other.update(entity_id='d::v',unit_id='d::v')
        catalog['records'].append(other)
        d=draft(category='multi_hop');d['evidence'].append(dict(d['evidence'][0],entity_id='d::v'))
        self.assertEqual(self.generate(catalog,[d])['manifest']['deferred'][0]['reason'],'INDEPENDENT_ARTICLES_REQUIRED')
        other['metadata']['dieu_number']='2'
        self.assertEqual(len(self.generate(catalog,[d])['records']),1)
        self.assertEqual(self.generate(catalog,[dict(d,rationale='')])['manifest']['deferred'][0]['reason'],'REASONING_RATIONALE_REQUIRED')

    def test_duplicate_questions_and_same_focus_drop_preserve_other_focus(self):
        a=draft();b=draft(qid='q2',question='  THEO nguồn synthetic, nội dung gì?  ')
        result=self.generate(drafts=[a,b]);self.assertEqual(len(result['records']),1)
        self.assertEqual(result['manifest']['duplicates'][0]['reason'],'DUPLICATE_QUESTION')
        b['question']='Cách diễn đạt khác?'
        self.assertEqual(self.generate(drafts=[a,b])['manifest']['duplicates'][0]['reason'],'DUPLICATE_FOCUS')
        b['focus']='Một tình huống khác'
        self.assertEqual(len(self.generate(drafts=[a,b])['records']),2)
        with self.assertRaises(module('models').ValidationError):self.generate(drafts=[a,a])

    def test_negative_requires_bounded_missing_authority_reason_no_positive_gold(self):
        negative=draft(qid='n',category='unanswerable',expected_abstain=True,expected_behavior='ABSTAIN',evidence=[],rationale='SAMPLE thiếu authority đã xác minh về hiệu lực.')
        rec=self.generate(drafts=[negative])['records'][0]
        self.assertEqual(rec['citation_gold'],[]);self.assertIsNone(rec['answer_reference'])
        for changes in ({'rationale':''},{'evidence':draft()['evidence']},{'expected_abstain':False}):
            with self.assertRaises(module('models').ValidationError):self.generate(drafts=[dict(negative,**changes)])

    def test_validation_detects_manifest_dataset_and_catalog_drift(self):
        result=self.generate();ds=module('dataset').dataset_from_records(result['records'])
        for key,value in (('dataset_hash','b'*64),('graph_fingerprint','b'*64),('category_counts',{})):
            bad=copy.deepcopy(result['manifest']);bad[key]=value
            with self.assertRaises(module('models').ValidationError):module('generation').validate_generated(ds,sources(),bad)

    def test_generated_freeze_requires_explicit_complete_review_receipt(self):
        ds=module('dataset').dataset_from_records(self.generate()['records'])
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'eval_questions.jsonl';source.write_bytes(ds.canonical_bytes)
            freeze=module('dataset').freeze_dataset
            with self.assertRaises(module('models').ValidationError):freeze(source,root,'frozen')
            review=dict(dataset_hash=ds.dataset_hash,reviewer='synthetic reviewer',reviewed_at='2026-10-12T00:00:00Z',approved_qids=['q1'])
            for change in ({'dataset_hash':'b'*64},{'approved_qids':[]},{'reviewer':''},{'reviewed_at':'bad'}):
                with self.assertRaises(module('models').ValidationError):freeze(source,root,'frozen',review_receipt=dict(review,**change))
            manifest=freeze(source,root,'frozen',review_receipt=review)
            frozen=module('dataset').load_dataset(manifest.with_name('eval_questions.jsonl'))
            self.assertFalse(frozen.official_benchmark)
            self.assertEqual(json.loads(frozen.records[0].notes)['review_status'],'APPROVED')
            self.assertEqual(source.read_bytes(),ds.canonical_bytes)

    def test_removing_tag_does_not_bypass_generation_review_gate(self):
        result=self.generate();payload=result['records'][0];payload['tags']=[]
        ds=module('dataset').dataset_from_records([payload])
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source.jsonl';source.write_bytes(ds.canonical_bytes)
            with self.assertRaises(module('models').ValidationError):module('dataset').freeze_dataset(source,root,'frozen')

if __name__=='__main__':unittest.main()
