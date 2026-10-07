"""Evaluation adapters: existing E and public F, with caller-supplied runtime."""
import math
import asyncio
from dataclasses import asdict
from datetime import date
from time import perf_counter

from .dataset import canonical_line, sha256, validate_catalog, strict_json
from .metrics import ranking_metrics, unavailable, answer_metrics, citation_metrics, citation_targets
from .models import EvaluationRun, QuestionResult, fail, text, boolean
from .report import start_run, validate_inputs, verify_snapshot, mark_run_error, write_report

CHANNELS = {'document':'gold_doc_ids','unit':'gold_unit_ids','sign':'gold_sign_ids'}


def _evidence(values, top_k):
    fields = {'entity_type','entity_id','doc_id','unit_id','sign_id','source_texts','score','vector_sources','graph_context'}
    if type(values) is not list or len(values) > top_k:
        fail('retrieval','INVALID_RETRIEVAL_OUTPUT')
    projected = {channel:[] for channel in CHANNELS}
    for value in values:
        if type(value) is not dict or set(value) != fields:
            fail('retrieval','INVALID_RETRIEVAL_OUTPUT')
        kind = value['entity_type']
        if kind not in ('VietRoadTraffic.LegalDocument','VietRoadTraffic.LegalUnit','VietRoadTraffic.TrafficSign'):
            fail('entity_type','INVALID_RETRIEVAL_OUTPUT')
        for name in ('entity_id','doc_id'):
            text(value[name],name,identity=True)
        for name in ('unit_id','sign_id'):
            if value[name] is not None:
                text(value[name],name,identity=True)
        if type(value['score']) not in (int,float) or not math.isfinite(value['score']) or not 0 <= value['score'] <= 1:
            fail('score','INVALID_RETRIEVAL_OUTPUT')
        if type(value['source_texts']) is not dict or any(type(k) is not str or type(v) is not str for k,v in value['source_texts'].items()):
            fail('source_texts','INVALID_RETRIEVAL_OUTPUT')
        if type(value['vector_sources']) is not list or type(value['graph_context']) is not list:
            fail('retrieval','INVALID_RETRIEVAL_OUTPUT')
        if kind.endswith('.LegalDocument') and (value['entity_id'] != value['doc_id'] or value['unit_id'] is not None or value['sign_id'] is not None):
            fail('entity_id','INVALID_RETRIEVAL_OUTPUT')
        if kind.endswith('.LegalUnit') and (value['entity_id'] != value['unit_id'] or value['sign_id'] is not None):
            fail('entity_id','INVALID_RETRIEVAL_OUTPUT')
        if kind.endswith('.TrafficSign') and value['entity_id'] != value['sign_id']:
            fail('entity_id','INVALID_RETRIEVAL_OUTPUT')
        projected['document'].append(value['doc_id'])
        if kind.endswith('.LegalUnit'):
            projected['unit'].append(value['unit_id'])
        if kind.endswith('.TrafficSign'):
            projected['sign'].append(value['sign_id'])
    canonical_line(values)
    return {channel:list(dict.fromkeys(v)) for channel,v in projected.items()}


def _error(row, exc):
    row.status = 'ERROR'
    row.error = {'type':type(exc).__name__,'code':'EXECUTION_ERROR'}
    row.eligibility['metric_eligibility'] = {name:metric.status != 'NOT_APPLICABLE' for name,metric in row.metrics.items()}
    row.metrics = {name:unavailable('EXECUTION_ERROR') for name in row.metrics}


def evaluate_g1(dataset, retriever, protocol, *, output_dir, identity_catalog=None):
    validate_inputs(dataset,protocol)
    if type(getattr(retriever,'search_k',None)) is not int or protocol.top_k > retriever.search_k or not callable(getattr(retriever,'retrieve',None)):
        fail('top_k','INVALID_CUTOFF')
    catalog = None
    if identity_catalog is not None:
        catalog = validate_catalog(identity_catalog)
        if sha256(canonical_line(identity_catalog)) != protocol.identity_catalog_hash:
            fail('identity_catalog_hash','CATALOG_HASH_MISMATCH')
    elif protocol.identity_catalog_hash is not None:
        fail('identity_catalog_hash','CATALOG_REQUIRED')
    context = start_run(dataset,protocol,'G1',output_dir)
    rows = []
    for record in dataset.records:
        row = QuestionResult(record.qid,record.category,record.source_group)
        for channel,field in CHANNELS.items():
            gold = getattr(record,field)
            missing = [g for g in gold if catalog is not None and g not in catalog[channel]]
            reason = 'NO_GOLD' if not gold else 'GOLD_OUTSIDE_CATALOG' if missing else None
            row.eligibility[channel] = {'eligible':bool(gold) and not missing,'reason':reason,'missing_gold':missing,'declared_gold_count':len(gold)}
            row.metrics.update({channel+'.'+name:unavailable(reason or 'NOT_EXECUTED','NOT_APPLICABLE' if reason else 'UNAVAILABLE') for name in ranking_metrics((),(),protocol.ks)})
        if any(v['eligible'] for v in row.eligibility.values()):
            verify_snapshot(context)
            started = perf_counter()
            try:
                values = retriever.retrieve(record.question,top_k=protocol.top_k,expand=False)
                projections = _evidence(values,protocol.top_k)
                values = strict_json(canonical_line(values))
                row.retrieval = {'evidence':values,'returned_count':len(values),'projections':projections,
                                 'channel_counts':{k:len(v) for k,v in projections.items()},'rank_semantics':protocol.rank_semantics}
                for channel,field in CHANNELS.items():
                    if row.eligibility[channel]['eligible']:
                        row.metrics.update({channel+'.'+name:metric for name,metric in ranking_metrics(getattr(record,field),tuple(projections[channel]),protocol.ks).items()})
                row.status = 'SUCCESS'
            except Exception as exc:
                _error(row,exc)
            row.latency_ms = (perf_counter()-started)*1000
        else:
            row.reasons = [v['reason'] for v in row.eligibility.values()]
        rows.append(row)
    return _complete(context,rows)


def _complete(context,rows):
    run = EvaluationRun(context,tuple(rows))
    write_report(run,context.output_dir)
    return run


def _g2_setup(dataset, pipeline, protocol, output_dir, judge):
    validate_inputs(dataset,protocol)
    if judge is not None and (not callable(judge) or protocol.judge_config is None):
        fail('judge','JUDGE_CONFIG_REQUIRED')
    if any(r.as_of for r in dataset.records):
        from kag.interface import SolverPipelineABC
        if not isinstance(pipeline,SolverPipelineABC):
            fail('pipeline','NATIVE_PIPELINE_REQUIRED')
    return start_run(dataset,protocol,'G2',output_dir)


def _g2_row(record):
    row = QuestionResult(record.qid,record.category,record.source_group)
    row.eligibility = {'g2':{'eligible':record.as_of is not None,'reason':None if record.as_of else 'AS_OF_REQUIRED'}}
    empty = {'answer':'','abstained':False}
    names = dict(answer_metrics(record,empty),**citation_metrics(record,()))
    row.metrics = {name:unavailable('NOT_EXECUTED' if record.as_of else 'AS_OF_REQUIRED') for name in names}
    if record.as_of is None:
        row.reasons = ['AS_OF_REQUIRED']
    return row


def _native(result):
    from kag.legal_solver import AnswerResult, Citation
    if not isinstance(result,AnswerResult) or type(result.citations) is not tuple:
        fail('answer_result','INVALID_NATIVE_RESULT')
    text(result.answer,'answer',blank=True)
    text(result.reason,'reason',blank=True)
    boolean(result.abstained,'abstained')
    citations = []
    for c in result.citations:
        if not isinstance(c,Citation):
            fail('citations','INVALID_NATIVE_RESULT')
        for name in ('doc_id','evidence_id'):
            text(getattr(c,name),name,identity=True)
        for name in ('unit_id','sign_id'):
            if getattr(c,name) is not None:
                text(getattr(c,name),name,identity=True)
        if c.field not in ('text','title','ten','moTa') or type(c.start) is not int or type(c.end) is not int or not 0 <= c.start < c.end:
            fail('citations','INVALID_NATIVE_SPAN')
        text(c.quote,'quote',blank=True)
        if len(c.quote) != c.end-c.start:
            fail('quote','INVALID_NATIVE_SPAN')
        citations.append(asdict(c))
    return dict(answer=result.answer,abstained=result.abstained,citations=citations,reason=result.reason)


def _g2_success(record,row,result,judge):
    native = _native(result)
    citations = tuple(native['citations'])
    row.metrics = dict(answer_metrics(record,native,judge),**citation_metrics(record,citations))
    row.eligibility.update(citation_targets(record,citations))
    row.answer_result = native
    row.status = 'SUCCESS'


def evaluate_g2(dataset, pipeline, protocol, *, output_dir, judge=None):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError('use await aevaluate_g2() inside an active event loop')
    context = _g2_setup(dataset,pipeline,protocol,output_dir,judge)
    rows = []
    for record in dataset.records:
        row = _g2_row(record)
        if record.as_of:
            from kag.legal_solver import answer
            verify_snapshot(context)
            started = perf_counter()
            try:
                result = answer(record.question,pipeline=pipeline,as_of=date.fromisoformat(record.as_of))
                _g2_success(record,row,result,judge)
            except Exception as exc:
                _error(row,exc)
            row.latency_ms = (perf_counter()-started)*1000
        rows.append(row)
    return _complete(context,rows)


async def aevaluate_g2(dataset, pipeline, protocol, *, output_dir, judge=None):
    context = _g2_setup(dataset,pipeline,protocol,output_dir,judge)
    rows = []
    for record in dataset.records:
        row = _g2_row(record)
        if record.as_of:
            from kag.legal_solver import aanswer
            verify_snapshot(context)
            started = perf_counter()
            try:
                result = await aanswer(record.question,pipeline=pipeline,as_of=date.fromisoformat(record.as_of))
                _g2_success(record,row,result,judge)
            except asyncio.CancelledError:
                mark_run_error(context,'CANCELLED')
                raise
            except Exception as exc:
                _error(row,exc)
            row.latency_ms = (perf_counter()-started)*1000
        rows.append(row)
    return _complete(context,rows)
