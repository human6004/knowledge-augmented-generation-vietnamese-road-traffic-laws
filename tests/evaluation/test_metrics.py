import unittest
from fixtures import module, record


def gold(doc,unit=None,required=True,span=None,sign=None):
    result = dict(doc_id=doc,unit_id=unit,sign_id=sign,required=required)
    if span:
        result.update(field='text',start=span[0],end=span[0]+len(span[1]),quote=span[1])
    return result


def citation(g):
    return {k:v for k,v in g.items() if k != 'required'}


class MetricTests(unittest.TestCase):
    def rec(self,**fields):
        return module('models').EvaluationRecord.from_dict(record(**fields))

    def test_bounded_rr(self):
        f = module('metrics').ranking_metrics
        result = f(('g1','g2'),('x','g2','g1'),(1,2,3))
        self.assertNotIn('MRR',result)
        for key,value in (('Hit@1',0),('Recall@2',.5),('MRR@2',.5),('returned_top_k_MRR',.5)):
            self.assertEqual(result[key].value,value)
        self.assertEqual(result['Recall@2'].denominator,2)
        self.assertIsNone(f((),(),(1,))['MRR@1'].value)
        self.assertEqual(f(('g',),(),(1,))['MRR@1'].value,0)
        self.assertEqual(f(('g',),('x','x','g'),(2,))['MRR@2'].value,.5)

    def test_multiple_required_optional_citations(self):
        a,b,c,x = gold('A','a',span=(0,'one')),gold('B','b',span=(0,'two')),gold('C','c',False),gold('X','x',span=(0,'bad'))
        result = module('metrics').citation_metrics(self.rec(citation_gold=[a,b,c]),tuple(map(citation,[a,c,x])))
        for key,n,d in (('citation_source_precision',2,3),('citation_source_recall',1,2),
                        ('citation_exact_precision',1,2),('citation_exact_recall',1,2)):
            self.assertEqual((result[key].numerator,result[key].denominator,result[key].value),(n,d,n/d))
        self.assertEqual(result['exact_excluded_citation_count'].value,1)

    def test_multiple_spans_same_source(self):
        a,b = gold('A','a',span=(0,'one')),gold('A','a',span=(4,'two'))
        r = module('metrics').citation_metrics(self.rec(citation_gold=[a,b]),(citation(a),citation(a)))
        self.assertEqual(r['citation_source_recall'].value,1)
        self.assertEqual(r['citation_exact_recall'].value,.5)
        self.assertEqual(r['citation_source_precision'].denominator,1)

    def test_optional_only_gold_and_no_citations(self):
        f = module('metrics').citation_metrics
        a = gold('A','a',False,span=(0,'one'))
        r = f(self.rec(citation_gold=[a]),(citation(a),))
        self.assertEqual(r['citation_source_precision'].value,1)
        self.assertEqual(r['citation_source_recall'].status,'NOT_APPLICABLE')
        self.assertIsNone(r['citation_exact_recall'].value)
        r = f(self.rec(citation_gold=[dict(a,required=True)]),())
        self.assertEqual(r['citation_source_recall'].value,0)
        self.assertEqual(r['citation_source_precision'].reason,'NO_CITATIONS')
        self.assertEqual(f(self.rec(),())['citation_source_precision'].status,'NOT_APPLICABLE')

    def test_citation_no_cross_pair_or_fuzzy_rescue(self):
        f = module('metrics').citation_metrics
        a,b = gold('A','a',span=(0,'é')),gold('B','b')
        rec = self.rec(citation_gold=[a,b])
        for wrong in (dict(citation(a),unit_id='b'),dict(citation(a),field='title'),
                      dict(citation(a),start=1,end=2),dict(citation(a),quote='e\u0301',end=2)):
            self.assertEqual(f(rec,(wrong,))['citation_exact_precision'].value,0)
        self.assertEqual(f(rec,(dict(citation(a),unit_id='b'),))['citation_source_precision'].value,0)
        with self.assertRaises(module('models').ValidationError):
            self.rec(citation_gold=[a,dict(a,required=False)])

    def test_partial_exact_gold_checkability_and_missing_levels(self):
        f = module('metrics').citation_metrics
        a = gold('A','a',span=(0,'one'))
        rec = self.rec(citation_gold=[a,gold('A','a'),gold('C','c',False)])
        wrong_span = dict(citation(a),quote='bad')
        r = f(rec,(wrong_span,citation(gold('C','c'))))
        self.assertEqual(r['citation_exact_precision'].value,0)
        self.assertEqual(r['citation_exact_precision'].denominator,1)
        r = f(rec,(citation(gold('A')),))
        self.assertEqual(r['citation_source_recall'].value,0)
        self.assertEqual(r['citation_unit_accuracy'].status,'UNAVAILABLE')
        sign = gold('A','anchor',sign='s')
        r = f(self.rec(citation_gold=[sign]),(citation(sign),))
        self.assertEqual(r['citation_sign_accuracy'].value,1)
        self.assertEqual(r['citation_unit_accuracy'].status,'NOT_APPLICABLE')
        self.assertEqual(r['citation_article_accuracy'].reason,'ARTICLE_IDENTITY_NOT_EXPOSED')

    def test_abstention_bool_matrix(self):
        f = module('metrics').answer_metrics
        for expected in (True,False):
            for actual in (True,False):
                r = f(self.rec(expected_abstain=expected),{'answer':'x','abstained':actual})
                self.assertEqual(r['abstention_accuracy'].value,float(expected == actual))
                if expected:
                    self.assertEqual(r['correct_abstention'].value,float(actual))
                    self.assertEqual(r['false_answer_rate'].value,float(not actual))
                else:
                    self.assertEqual(r['wrong_abstention_rate'].value,float(actual))

    def test_judge_optional_unknown_error(self):
        f = module('metrics').answer_metrics
        rec = self.rec(answer_reference={'expected_answer':'answer'})
        answer = {'answer':'x','abstained':False}
        self.assertEqual(f(rec,answer)['answer_correctness'].reason,'JUDGE_NOT_CONFIGURED')
        for judge in (lambda **k: {'verdict':'UNKNOWN','rationale':'undecided'},lambda **k:{'verdict':'BAD'},lambda **k:1):
            r = f(rec,answer,judge)['answer_correctness']
            self.assertIsNone(r.value)
        def broken(**kwargs):
            raise ValueError('SECRET')
        self.assertEqual(f(rec,answer,broken)['answer_correctness'].reason,'JUDGE_ERROR')
        self.assertEqual(f(self.rec(),answer,broken)['answer_correctness'].reason,'NO_ANSWER_REFERENCE')
        self.assertEqual(f(rec,answer,lambda **k:{'verdict':'SUPPORTED','rationale':'ok'})['answer_correctness'].value,1)

    def test_marker_diagnostic_preserves_legal_tokens(self):
        r = module('metrics').answer_metrics(self.rec(answer_reference={'markers':['30,5%','30.000.000','không']}),
                                             {'answer':'305% 3.000.000 có','abstained':False})
        self.assertEqual(r['marker_coverage'].value,0)
        self.assertIsNone(r['answer_correctness'].value)
        r = module('metrics').answer_metrics(self.rec(answer_reference={'markers':['É không']}),
                                             {'answer':'E\u0301  KHÔNG','abstained':False})
        self.assertEqual(r['marker_coverage'].value,1)
        self.assertEqual(r['markers_all'].value,1)


if __name__ == '__main__':
    unittest.main()
