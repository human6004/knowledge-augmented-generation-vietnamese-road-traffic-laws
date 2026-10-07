import copy
import unittest
from fixtures import module


def legacy(**changes):
    value = dict(id='L1',question='Câu hỏi legacy synthetic?',category='definition',answerable=True,
                 gold_evidence=[dict(document_id='123/2026/SYN',article='1',clause=None,point=None,text='Nguồn synthetic.',required=True)],
                 gold_markers=['synthetic'],verification_status='CORPUS_VERIFIED')
    value.update(changes)
    return value


def mapping(required=True):
    d = module('dataset')
    catalog = dict(schema_version='1.0',identities=dict(document=['d'],unit=['u'],sign=[]))
    bundle = dict(schema_version='1.0',current_catalog_hash=d.sha256(d.canonical_line(catalog)),
                  entries=[dict(legacy_reference=legacy()['gold_evidence'][0],citation=dict(doc_id='d',unit_id='u',required=required))])
    return bundle,catalog


class LegacyTests(unittest.TestCase):
    def test_multiple_locators_same_target_dedup_required_or(self):
        f = module('legacy').import_legacy
        bundle,catalog=mapping()
        value=legacy()
        second=dict(value['gold_evidence'][0],article='2',required=False)
        value['gold_evidence'].append(second)
        bundle['entries'].append(dict(legacy_reference=second,citation=dict(doc_id='d',unit_id='u',required=False)))
        result=f([value],dataset_version='v',as_of='2026-10-06',mapping=bundle,current_catalog=catalog)
        self.assertEqual(result['counts']['converted'],1)
        self.assertEqual(len(result['converted'][0]['legacy_references']),2)
        self.assertEqual(len(result['converted'][0]['citation_gold']),1)
        self.assertTrue(result['converted'][0]['citation_gold'][0]['required'])
        for index,entry in enumerate(bundle['entries']):
            entry['citation'].update(field='text',start=index*4,end=index*4+3,quote=('one','two')[index])
        result=f([value],dataset_version='v',as_of='2026-10-06',mapping=bundle,current_catalog=catalog)
        self.assertEqual(len(result['converted'][0]['citation_gold']),2)

    def test_whitelisted_provenance_kept_for_converted_and_manual(self):
        f = module('legacy').import_legacy
        bundle,catalog=mapping()
        provenance=dict(origin='legacy_pass',candidate_id='C1',legacy_id='OLD1',fix_action=None,verification_status='CORPUS_VERIFIED')
        value=legacy(**provenance)
        for kwargs in ({},{'as_of':'2026-10-06','mapping':bundle,'current_catalog':catalog}):
            result=f([value],dataset_version='v',**kwargs)
            self.assertIn('record_provenance',result)
            self.assertEqual(result['record_provenance'][0]['provenance'],provenance)
            self.assertEqual(result['record_provenance'][0]['legacy_id'],'L1')
            self.assertFalse(result['provenance']['official_benchmark'])

    def test_declared_legacy_claims_sources_evidence_labels(self):
        f = module('legacy').import_legacy
        bundle,catalog=mapping()
        value=legacy(gold_claims=['Authored legacy fact'],source_name='Legacy source',source_url='https://example.invalid/source')
        value['gold_evidence'][0]['evidence_id']='OLD-LABEL'
        result=f([value],dataset_version='v',as_of='2026-10-06',mapping=bundle,current_catalog=catalog)
        self.assertEqual(result['counts']['converted'],1)
        converted=result['converted'][0]
        self.assertEqual(converted['answer_reference']['accepted_facts'],['Authored legacy fact'])
        self.assertEqual(converted['source_group'],'Legacy source')
        self.assertNotIn('evidence_id',converted['citation_gold'][0])
        self.assertEqual(result['record_provenance'][0]['legacy_evidence_ids'],['OLD-LABEL'])
        self.assertEqual(result['record_provenance'][0]['source_url'],value['source_url'])

    def test_import_no_invented_gold(self):
        f = module('legacy').import_legacy
        result = f([legacy(),{'input':'question','answers':['prediction']},legacy(id='L3',verification_status='PENDING')],dataset_version='provisional')
        self.assertEqual(len(result['converted']),0)
        self.assertEqual(len(result['needs_manual_mapping']),2)
        self.assertEqual(len(result['rejected']),1)
        refs = result['needs_manual_mapping'][0]['legacy_references']
        self.assertEqual(refs[0]['document_id'],'123/2026/SYN')
        self.assertIn('AS_OF_REQUIRED',result['needs_manual_mapping'][0]['reasons'])
        for changes in ({'category':'unknown'},{'chunk_id':'old'},{'outputs':['prediction']},{'gold_markers':['']},
                        {'gold_evidence':[]},{'answerable':'true'}):
            self.assertEqual(len(f([legacy(**changes)],dataset_version='v')['rejected']),1)

    def test_explicit_mapping_converts_provisional_only(self):
        f = module('legacy').import_legacy
        bundle,catalog = mapping()
        result = f([legacy()],dataset_version='provisional',as_of='2026-10-06',mapping=bundle,current_catalog=catalog)
        self.assertEqual(len(result['converted']),1)
        value = result['converted'][0]
        self.assertEqual(value['dataset_status'],'PROVISIONAL')
        self.assertEqual(value['gold_unit_ids'],['u'])
        self.assertEqual(value['gold_doc_ids'],['d'])
        self.assertFalse(value['expected_abstain'])
        self.assertEqual(value['question'],legacy()['question'])
        module('dataset').dataset_from_records(result['converted'])
        bundle['entries']=[]
        result=f([legacy()],dataset_version='p',as_of='2026-10-06',mapping=bundle,current_catalog=catalog)
        self.assertEqual(len(result['needs_manual_mapping']),1)
        self.assertIn('UNMAPPED_REFERENCE',result['needs_manual_mapping'][0]['reasons'])

    def test_mapping_stale_ambiguous_type_coercion_rejected(self):
        f,m = module('legacy').import_legacy,module('models')
        bundle,catalog = mapping()
        for changes in ({'current_catalog_hash':'0'*64},{'entries':bundle['entries']*2},
                        {'entries':[dict(bundle['entries'][0],citation={'doc_id':'missing'})]},
                        {'entries':[dict(bundle['entries'][0],legacy_reference=dict(legacy()['gold_evidence'][0],article=1))]}):
            with self.assertRaises(m.ValidationError):
                f([legacy()],dataset_version='v',as_of='2026-10-06',mapping=dict(bundle,**changes),current_catalog=catalog)
        bundle,catalog=mapping(False)
        with self.assertRaises(m.ValidationError):
            f([legacy()],dataset_version='v',as_of='2026-10-06',mapping=bundle,current_catalog=catalog)

    def test_optional_required_mapping_and_no_fabricated_unanswerable(self):
        f = module('legacy').import_legacy
        bundle,catalog=mapping(False)
        bundle['entries'][0]['legacy_reference']['required']=False
        value=legacy()
        value['gold_evidence'][0]['required']=False
        result=f([value],dataset_version='v',as_of='2026-10-06',mapping=bundle,current_catalog=catalog)
        self.assertFalse(result['converted'][0]['citation_gold'][0]['required'])
        result=f([legacy(answerable=False,gold_evidence=[],gold_markers=[])],dataset_version='v',as_of='2026-10-06')
        self.assertTrue(result['converted'][0]['expected_abstain'])
        self.assertEqual(result['converted'][0]['citation_gold'],[])


if __name__ == '__main__':
    unittest.main()
