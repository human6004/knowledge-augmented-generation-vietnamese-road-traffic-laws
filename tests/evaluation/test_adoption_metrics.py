import tempfile
from pathlib import Path
import unittest
from fixtures import module, record


class AdoptionMetricTests(unittest.TestCase):
    def test_macro_category_mean_and_execution_outcomes_opt_in(self):
        from types import SimpleNamespace
        m=module('models');r=module('report')
        rows=(m.QuestionResult('a','definition',status='SUCCESS',metrics={'quality':m.MetricValue(0,'OK')},reasons=['ANSWERED']),
              m.QuestionResult('b','definition',status='SUCCESS',metrics={'quality':m.MetricValue(0,'OK')},reasons=['UNANSWERED']),
              m.QuestionResult('c','multi_hop',status='SUCCESS',metrics={'quality':m.MetricValue(1,'OK')},reasons=['ABSTAINED']))
        dataset=module('dataset').dataset_from_records([record(qid=row.qid,category=row.category) for row in rows])
        ctx=SimpleNamespace(dataset=dataset,protocol=m.EvaluationProtocol(metric_policy_version='1.1'))
        result=r.summarize(m.EvaluationRun(ctx,rows))
        self.assertEqual(result['overall']['quality']['value'],1/3)
        self.assertEqual(result['macro']['quality']['value'],.5)
        self.assertEqual(result['macro']['quality']['scored_category_count'],2)
        self.assertEqual(result['execution_outcomes'],{'answered':1,'abstained':1,'unanswered':1,'error':0})
        ctx.protocol=m.EvaluationProtocol()
        self.assertNotIn('macro',r.summarize(m.EvaluationRun(ctx,rows)))

    def rec(self,**changes):return module('models').EvaluationRecord.from_dict(record(**changes))

    def test_span_formulas_required_optional_mixed_rank_and_no_gold(self):
        gold=[dict(doc_id='d',unit_id='u',field='text',start=0,end=3,quote='one'),
              dict(doc_id='d',unit_id='v',field='text',start=0,end=3,quote='two',required=False)]
        evidence=[dict(doc_id='x',unit_id='x',sign_id=None,source_texts={'text':'one'}),
                  dict(doc_id='d',unit_id='v',sign_id=None,source_texts={'text':'two'}),
                  dict(doc_id='d',unit_id='u',sign_id=None,source_texts={'text':'prefix one suffix'})]
        f=module('metrics').source_span_metrics
        result=f(self.rec(citation_gold=gold),evidence,(1,2,3))
        expected={'evidence_recall':1,'evidence_recall_required':1,'context_precision':2/3,
                  'Hit@1':0,'Hit@2':0,'Hit@3':1,'Recall@2':.5,'returned_top_k_MRR':1/3}
        for name,value in expected.items():self.assertEqual(result[name].value,value,name)
        self.assertEqual((result['Recall@2'].numerator,result['Recall@2'].denominator),(1,2))
        self.assertEqual(f(self.rec(citation_gold=gold),[],(1,))['evidence_recall'].value,0)
        self.assertEqual(f(self.rec(citation_gold=gold),[],(1,))['context_precision'].status,'UNAVAILABLE')
        self.assertEqual(f(self.rec(),evidence,(1,))['Hit@1'].status,'NOT_APPLICABLE')

    def test_exact_span_support_not_fuzzy_or_wrong_public_identity(self):
        rec=self.rec(citation_gold=[dict(doc_id='d',unit_id='u',field='text',start=0,end=len('không phạt 30.000 đồng.'),quote='không phạt 30.000 đồng.')])
        f=module('metrics').source_span_metrics
        for item in (dict(doc_id='d',unit_id='u',sign_id=None,source_texts={'text':'phạt 30.000 đồng.'}),
                     dict(doc_id='d',unit_id='v',sign_id=None,source_texts={'text':'không phạt 30.000 đồng.'})):
            self.assertEqual(f(rec,[item],(1,))['evidence_recall'].value,0)

    def test_policy1_0_unchanged_and_1_1_blank_is_unanswered(self):
        f=module('metrics').answer_metrics
        rec=self.rec(expected_abstain=True)
        empty={'answer':'   ','abstained':False}
        self.assertEqual(f(rec,empty)['false_answer_rate'].value,1)
        result=f(rec,empty,metric_policy_version='1.1')
        for name in ('false_answer_rate','correct_abstention','abstention_accuracy'):
            self.assertIsNone(result[name].value);self.assertEqual(result[name].reason,'UNANSWERED')
        abstain=f(rec,dict(empty,abstained=True),metric_policy_version='1.1')
        self.assertEqual(abstain['correct_abstention'].value,1)
        with self.assertRaises(module('models').ValidationError):module('models').EvaluationProtocol(metric_policy_version='future')
        self.assertEqual(module('models').EvaluationProtocol(metric_policy_version='1.1').metric_policy_version,'1.1')

    def test_g1_new_metrics_opt_in_preserves_old_keys(self):
        class Retriever:
            search_k=1
            def retrieve(self,question,**kwargs):
                self.question=question
                return [dict(entity_type='VietRoadTraffic.LegalUnit',entity_id='u',doc_id='d',unit_id='u',sign_id=None,
                    source_texts={'text':'one'},score=.5,vector_sources=[],graph_context=[])]
        ds=module('dataset').dataset_from_records([record(gold_unit_ids=['u'],citation_gold=[dict(doc_id='d',unit_id='u',field='text',start=0,end=3,quote='one')])])
        with tempfile.TemporaryDirectory() as temp:
            for version in ('1.0','1.1'):
                retriever=Retriever()
                protocol=module('models').EvaluationProtocol(ks=(1,),top_k=1,metric_policy_version=version)
                run=module('evaluate').evaluate_g1(ds,retriever,protocol,output_dir=Path(temp)/version)
                metrics=run.rows[0].metrics
                self.assertEqual('source_span.evidence_recall' in metrics,version=='1.1')
                if version=='1.1':self.assertEqual(metrics['source_span.evidence_recall'].value,1)
                self.assertEqual(retriever.question,ds.records[0].question)

    def test_source_span_gold_outside_catalog_not_scored_via_document_coverage(self):
        class Retriever:
            search_k=1
            def retrieve(self,*args,**kwargs):return []
        d=module('dataset');m=module('models')
        ds=d.dataset_from_records([record(gold_doc_ids=['d'],gold_unit_ids=['missing'],citation_gold=[dict(doc_id='d',unit_id='missing',field='text',start=0,end=3,quote='one')])])
        catalog={'schema_version':'1.0','identities':{'document':['d'],'unit':[],'sign':[]}}
        protocol=m.EvaluationProtocol(ks=(1,),top_k=1,metric_policy_version='1.1',identity_catalog_hash=d.sha256(d.canonical_line(catalog)))
        with tempfile.TemporaryDirectory() as temp:
            row=module('evaluate').evaluate_g1(ds,Retriever(),protocol,output_dir=Path(temp)/'run',identity_catalog=catalog).rows[0]
            metric=row.metrics['source_span.evidence_recall']
            self.assertIsNone(metric.value);self.assertEqual(metric.reason,'GOLD_OUTSIDE_CATALOG')

    def test_g2_outcome_native_bool_and_unanswered_not_error(self):
        from kag.bootstrap import initialize
        initialize()
        from kag.interface import SolverPipelineABC
        from kag.legal_solver import AnswerResult
        class Pipeline(SolverPipelineABC):
            async def ainvoke(self,*args,**kwargs):return AnswerResult('',(),False)
        ds=module('dataset').dataset_from_records([record(as_of='2026-10-12',expected_abstain=True)])
        with tempfile.TemporaryDirectory() as temp:
            run=module('evaluate').evaluate_g2(ds,Pipeline(),module('models').EvaluationProtocol(metric_policy_version='1.1'),output_dir=Path(temp)/'run')
            row=run.rows[0];self.assertEqual(row.status,'SUCCESS');self.assertIn('UNANSWERED',row.reasons)
            self.assertIsNone(row.metrics['false_answer_rate'].value)

    def test_g2_error_keeps_metric_applicability_denominators(self):
        from kag.bootstrap import initialize
        initialize()
        from kag.interface import SolverPipelineABC
        class Pipeline(SolverPipelineABC):
            async def ainvoke(self,*args,**kwargs):raise ValueError('synthetic execution error')
        ds=module('dataset').dataset_from_records([record(as_of='2026-10-12',expected_abstain=False)])
        with tempfile.TemporaryDirectory() as temp:
            run=module('evaluate').evaluate_g2(ds,Pipeline(),module('models').EvaluationProtocol(metric_policy_version='1.1'),output_dir=Path(temp)/'run')
            metrics=module('report').summarize(run)['overall']
            self.assertEqual(metrics['correct_abstention']['eligible_count'],0)
            self.assertEqual(metrics['false_answer_rate']['failed_count'],0)
            self.assertEqual(metrics['wrong_abstention_rate']['eligible_count'],1)
            self.assertEqual(metrics['wrong_abstention_rate']['failed_count'],1)
            self.assertEqual(metrics['citation_exact_recall']['eligible_count'],0)

if __name__=='__main__':unittest.main()
