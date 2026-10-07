"""Exact identities/spans and bounded rankings; lexical signals are diagnostic."""
from kag.retriever.evaluation import evaluate as exact_ranking
import unicodedata
from .models import MetricValue

IDENTITY = ('doc_id','unit_id','sign_id')
FULL = IDENTITY + ('field','start','end','quote')


def unavailable(reason, status='UNAVAILABLE', denominator=None):
    return MetricValue(status=status,denominator=denominator,reason=reason)


def fraction(n, d, *, empty='NO_PREDICTIONS', applicable=True):
    if not applicable:
        return unavailable('NO_GOLD','NOT_APPLICABLE')
    if not d:
        return unavailable(empty,denominator=0)
    return MetricValue(n/d,'OK',n,d)


def count(n):
    return MetricValue(float(n),'OK',n,1)


def ranking_metrics(gold, ranked, ks):
    ranked = tuple(dict.fromkeys(ranked))
    names = ['returned_top_k_MRR']+[name for k in ks for name in (f'Hit@{k}',f'Recall@{k}',f'MRR@{k}')]
    if not gold:
        return {name:unavailable('NO_GOLD','NOT_APPLICABLE') for name in names}
    values = exact_ranking([{'qid':'row','gold_unit_ids':list(gold)}],
                           [{'qid':'row','unit_ids':list(ranked)}],ks)['overall']
    rank = next((i for i,v in enumerate(ranked,1) if v in gold),None)
    result = {'returned_top_k_MRR':MetricValue(values['MRR'],'OK',1 if rank else 0,rank or 1)}
    for k in ks:
        matches = len(set(gold) & set(ranked[:k]))
        result[f'Hit@{k}'] = fraction(int(matches>0),1)
        result[f'Recall@{k}'] = fraction(matches,len(gold))
        result[f'MRR@{k}'] = MetricValue(values[f'MRR@{k}'],'OK',1 if rank and rank<=k else 0,rank if rank and rank<=k else 1)
    return result


def identity_match(citation, gold):
    return citation.get('doc_id') == gold['doc_id'] and all(gold.get(k) is None or citation.get(k) == gold[k] for k in ('unit_id','sign_id'))


def key(value, names=FULL):
    return tuple(value.get(k) for k in names)


def unique(values, names=FULL):
    return list({key(v,names):v for v in values}.values())


def citation_targets(record, citations):
    gold = [g.to_dict() for g in record.citation_gold]
    required = unique([g for g in gold if g['required']],IDENTITY)
    exact = unique([g for g in gold if g['required'] and g['field'] is not None])
    return dict(missing_required_sources=[{k:g[k] for k in IDENTITY} for g in required if not any(identity_match(c,g) for c in citations)],
                missing_required_spans=[g for g in exact if not any(key(c)==key(g) for c in citations)])


def citation_metrics(record, citations):
    gold = [g.to_dict() for g in record.citation_gold]
    acceptable = unique(gold,IDENTITY)
    required = unique([g for g in gold if g['required']],IDENTITY)
    predicted = unique(citations,IDENTITY)
    full = unique(citations)
    exact = unique([g for g in gold if g['field'] is not None])
    required_exact = unique([g for g in exact if g['required']])
    checkable = [c for c in full if any(identity_match(c,g) for g in exact) or not any(identity_match(c,g) for g in acceptable)] if exact else []
    result = {
        'citation_source_precision':fraction(sum(any(identity_match(c,g) for g in acceptable) for c in predicted),len(predicted),empty='NO_CITATIONS',applicable=bool(acceptable)),
        'citation_source_recall':fraction(sum(any(identity_match(c,g) for c in predicted) for g in required),len(required),applicable=bool(required)),
        'citation_exact_precision':fraction(sum(any(key(c)==key(g) for g in exact) for c in checkable),len(checkable),empty='NO_CHECKABLE_CITATIONS',applicable=bool(exact)),
        'citation_exact_recall':fraction(sum(any(key(c)==key(g) for c in full) for g in required_exact),len(required_exact),applicable=bool(required_exact)),
        'exact_eligible_citation_count':count(len(checkable)),
        'exact_excluded_citation_count':MetricValue(float(len(full)-len(checkable)),'OK',len(full)-len(checkable),1,
                                                   'EXACT_GOLD_NOT_AVAILABLE_FOR_SOURCE' if len(full)>len(checkable) else None),
        'required_source_count':count(len(required)), 'acceptable_source_count':count(len(acceptable)),
        'citation_article_accuracy':unavailable('ARTICLE_IDENTITY_NOT_EXPOSED'),
    }
    for level,names in (('doc',('doc_id',)),('unit',('doc_id','unit_id')),('sign',IDENTITY)):
        def at_level(v):
            return level == 'doc' or (v.get('unit_id') is not None and v.get('sign_id') is None if level == 'unit' else v.get('sign_id') is not None)
        targets = unique([g for g in gold if at_level(g)],names)
        predictions = unique([c for c in predicted if at_level(c)],names)
        def match(c,g):
            if level == 'doc':
                return c.get('doc_id') == g['doc_id']
            return identity_match(c,g)
        result[f'citation_{level}_accuracy'] = fraction(sum(any(match(c,g) for g in targets) for c in predictions),len(predictions),applicable=bool(targets))
    return result


def answer_metrics(record, answer_result, judge=None):
    actual, expected = answer_result['abstained'], record.expected_abstain
    result = {'abstention_accuracy':fraction(int(actual == expected),1),
              'correct_abstention':fraction(int(actual),1,applicable=expected),
              'false_answer_rate':fraction(int(not actual),1,applicable=expected),
              'wrong_abstention_rate':fraction(int(actual),1,applicable=not expected),
              'grounding':unavailable('FULL_TRACE_NOT_EXPOSED')}
    reference = record.answer_reference
    markers = reference.markers if reference else ()
    def presentation(value):
        return ' '.join(unicodedata.normalize('NFC',value).casefold().split())
    hits = sum(presentation(m) in presentation(answer_result['answer']) for m in markers)
    result['marker_coverage'] = fraction(hits,len(markers),applicable=bool(markers))
    result['markers_all'] = fraction(int(hits == len(markers)),1,applicable=bool(markers))
    if reference is None or not (reference.expected_answer or reference.accepted_facts):
        result['answer_correctness'] = unavailable('NO_ANSWER_REFERENCE')
    elif judge is None:
        result['answer_correctness'] = unavailable('JUDGE_NOT_CONFIGURED')
    else:
        try:
            decision = judge(question=record.question,answer=answer_result['answer'],reference=reference.to_dict())
            if type(decision) is not dict or set(decision) != {'verdict','rationale'} or type(decision['rationale']) is not str or decision['verdict'] not in ('SUPPORTED','NOT_SUPPORTED','CONTRADICTED','UNKNOWN'):
                raise ValueError('invalid judge response')
            verdict = decision['verdict']
            result['answer_correctness'] = unavailable('JUDGE_UNDECIDED','UNKNOWN') if verdict == 'UNKNOWN' else fraction(int(verdict == 'SUPPORTED'),1)
        except Exception:
            result['answer_correctness'] = unavailable('JUDGE_ERROR')
    return result
