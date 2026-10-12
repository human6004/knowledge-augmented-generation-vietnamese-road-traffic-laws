"""Offline B2 evidence-first authoring: drafts propose questions, sources supply gold."""
from collections import Counter
import unicodedata

from .dataset import canonical_line, dataset_from_records, sha256, strict_json
from .models import CATEGORIES, CitationGold, boolean, calendar, fail, ids, obj, text

METHOD = 'legacy-b2-evidence-first-adapted'
VERSION = '1.0'


def _hash(value, name):
    if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        fail(name, 'INVALID_HASH')
    return value


def _question(value):
    return ' '.join(unicodedata.normalize('NFC', value).casefold().split())


def _sources(catalog):
    if type(catalog) is not dict or catalog.get('schema') != 'h1-source-catalog-1.0':
        fail('catalog', 'UNSUPPORTED_SCHEMA')
    _hash(catalog.get('graph_fingerprint'), 'graph_fingerprint')
    text(catalog.get('source_snapshot_id'), 'source_snapshot_id', identity=True)
    if type(catalog.get('records')) is not list:
        fail('records')
    result = {}
    for source in catalog['records']:
        if type(source) is not dict:
            fail('source')
        for name in ('entity_id', 'doc_id'):
            text(source.get(name), name, identity=True)
        kind = source.get('entity_type')
        doc, unit, sign = (source.get(name) for name in ('doc_id', 'unit_id', 'sign_id'))
        identity = source['entity_id']
        valid = ((kind == 'VietRoadTraffic.LegalDocument' and identity == doc and unit is None and sign is None)
                 or (kind == 'VietRoadTraffic.LegalUnit' and identity == unit and sign is None)
                 or (kind == 'VietRoadTraffic.TrafficSign' and identity == sign))
        if not valid:
            fail('source', 'SOURCE_IDENTITY_MISMATCH')
        for name in ('unit_id', 'sign_id'):
            if source.get(name) is not None:
                text(source[name], name, identity=True)
        content = text(source.get('source_text'), 'source_text')
        if sha256(content.encode('utf-8')) != source.get('source_sha256'):
            fail('source_sha256', 'SOURCE_HASH_MISMATCH')
        # The sealed catalog uses logical mo_ta; native citations use schema moTa.
        field = 'moTa' if kind == 'VietRoadTraffic.TrafficSign' and source.get('field') == 'mo_ta' and source.get('physical_field') == 'moTa' else source.get('field')
        source = dict(source, field=field)
        CitationGold.from_dict(dict(doc_id=doc, unit_id=unit, sign_id=sign, field=field,
                                    start=0, end=len(content), quote=content))
        if type(source.get('metadata', {})) is not dict:
            fail('metadata')
        key = (kind, identity, source['field'])
        if key in result:
            fail('source', 'AMBIGUOUS_SOURCE')
        result[key] = source
    return result


def generate_questions(catalog, drafts, config, *, source_catalog_sha256=None):
    """Assemble author drafts against exact spans; never invoke a model or a graph writer."""
    obj(config, ('dataset_version', 'as_of', 'categories'), ('dataset_version', 'as_of', 'categories'))
    text(config['dataset_version'], 'dataset_version', identity=True)
    calendar(config['as_of'])
    if config['as_of'] is None:
        fail('as_of', 'AS_OF_REQUIRED')
    categories = ids(config['categories'], 'categories')
    if not categories or set(categories) - set(CATEGORIES):
        fail('categories', 'INVALID_CATEGORY')
    sources = _sources(catalog)
    catalog_hash = source_catalog_sha256 or sha256(canonical_line(catalog))
    _hash(catalog_hash, 'source_catalog_sha256')
    if type(drafts) is not list or not drafts:
        fail('drafts', 'EMPTY_DATASET')
    records, deferred, duplicates = [], [], []
    seen_ids, seen_questions, seen_focus = set(), set(), set()
    for draft in drafts:
        fields = ('qid', 'question', 'category', 'expected_abstain', 'expected_behavior', 'focus', 'rationale', 'evidence')
        obj(draft, fields, fields)
        qid = text(draft['qid'], 'qid', identity=True)
        if qid in seen_ids:
            fail('qid', 'DUPLICATE_QID')
        seen_ids.add(qid)
        text(draft['question'], 'question')
        text(draft['focus'], 'focus')
        text(draft['rationale'], 'rationale', blank=True)
        boolean(draft['expected_abstain'], 'expected_abstain')
        if draft['category'] not in categories:
            fail('category', 'INVALID_CATEGORY')
        if type(draft['evidence']) is not list:
            fail('evidence')
        negative = draft['expected_abstain']
        if negative:
            if (draft['category'] != 'unanswerable' or draft['expected_behavior'] != 'ABSTAIN'
                    or draft['evidence'] or not draft['rationale'].strip()):
                fail('draft', 'NEGATIVE_SCOPE_REASON_REQUIRED')
        elif draft['category'] == 'unanswerable' or draft['expected_behavior'] != 'EXTRACT_ONLY' or not draft['evidence']:
            fail('draft', 'EXACT_SOURCE_GOLD_REQUIRED')
        gold, provenance, locations, missing = [], [], set(), False
        for span in draft['evidence']:
            keys = ('entity_type', 'entity_id', 'field', 'start', 'end', 'required')
            obj(span, keys, keys)
            for name in ('entity_type', 'entity_id', 'field'):
                text(span[name], name, identity=True)
            boolean(span['required'], 'required')
            start, end = span['start'], span['end']
            if type(start) is not int or type(end) is not int or not 0 <= start < end:
                fail('span', 'INVALID_SPAN')
            source = sources.get((span['entity_type'], span['entity_id'], span['field']))
            if source is None:
                missing = True
                continue
            if end > len(source['source_text']):
                fail('span', 'INVALID_SPAN')
            citation = CitationGold.from_dict(dict(doc_id=source['doc_id'], unit_id=source.get('unit_id'),
                sign_id=source.get('sign_id'), field=span['field'], start=start, end=end,
                quote=source['source_text'][start:end], required=span['required']))
            gold.append(citation.to_dict())
            metadata = source.get('metadata', {})
            article = metadata.get('dieu_number')
            if article is not None and span['required']:
                locations.add((source['doc_id'], str(article)))
            provenance.append(dict(span, doc_id=source['doc_id'], source_sha256=source['source_sha256'],
                                   source_record=metadata.get('source_record'), article=article))
        reason = ('SOURCE_NOT_AVAILABLE' if missing else
                  'INDEPENDENT_ARTICLES_REQUIRED' if draft['category'] == 'multi_hop' and len(locations) < 2 else
                  'REASONING_RATIONALE_REQUIRED' if draft['category'] in ('multi_hop', 'inter_document') and not draft['rationale'].strip() else None)
        if reason:
            deferred.append(dict(qid=qid, category=draft['category'], reason=reason))
            continue
        if not negative and not any(g['required'] for g in gold):
            fail('evidence', 'REQUIRED_GOLD_MISSING')
        question_key = _question(draft['question'])
        focus_key = (draft['category'], _question(draft['focus']), canonical_line(sorted(gold, key=lambda g: canonical_line(g))))
        duplicate = ('DUPLICATE_QUESTION' if question_key in seen_questions else 'DUPLICATE_FOCUS' if focus_key in seen_focus else None)
        if duplicate:
            duplicates.append(dict(qid=qid, reason=duplicate))
            continue
        seen_questions.add(question_key)
        seen_focus.add(focus_key)
        notes = dict(generation_method=METHOD, generation_version=VERSION, review_status='PROVISIONAL', human_reviewed=False,
            applicability='NOT_VERIFIED', expected_behavior=draft['expected_behavior'], focus=draft['focus'], rationale=draft['rationale'],
            graph_fingerprint=catalog['graph_fingerprint'], source_snapshot_id=catalog['source_snapshot_id'],
            source_catalog_sha256=catalog_hash, source_spans=provenance)
        records.append(dict(schema_version='1.0', dataset_version=config['dataset_version'], dataset_status='PROVISIONAL',
            qid=qid, question=draft['question'], category=draft['category'], expected_abstain=negative, as_of=config['as_of'],
            gold_doc_ids=list(dict.fromkeys(g['doc_id'] for g in gold)),
            gold_unit_ids=list(dict.fromkeys(g['unit_id'] for g in gold if g['unit_id'])),
            gold_sign_ids=list(dict.fromkeys(g['sign_id'] for g in gold if g['sign_id'])), citation_gold=gold,
            answer_reference=None if negative else {'accepted_facts': list(dict.fromkeys(g['quote'] for g in gold if g['required']))},
            source_group=catalog['source_snapshot_id'], notes=canonical_line(notes).decode('utf-8').strip(),
            tags=['PROVISIONAL', 'NO_HUMAN_REVIEW', 'EVIDENCE_FIRST']))
    dataset = dataset_from_records(records) if records else None
    records = [r.to_dict() for r in dataset.records] if dataset else []
    counts = Counter(r['category'] for r in records)
    manifest = dict(schema_version='1.0', method=METHOD, generation_version=VERSION, config=config, drafts=drafts,
        source_catalog_sha256=catalog_hash, graph_fingerprint=catalog['graph_fingerprint'], source_snapshot_id=catalog['source_snapshot_id'],
        dataset_hash=dataset.dataset_hash if dataset else None, requested_count=len(drafts), generated_count=len(records),
        category_counts={c:counts[c] for c in CATEGORIES}, deferred=deferred, duplicates=duplicates,
        review_status='PROVISIONAL', human_reviewed=False, official_benchmark=False, paper_eligible=False)
    # Snapshot caller-owned objects; later mutation must not rewrite provenance.
    return strict_json(canonical_line(dict(records=records, manifest=manifest)))


def validate_generated(dataset, catalog, manifest, *, source_catalog_sha256=None):
    if type(manifest) is not dict:
        fail('generation_manifest')
    rebuilt = generate_questions(catalog, manifest.get('drafts'), manifest.get('config'), source_catalog_sha256=source_catalog_sha256)
    if rebuilt['manifest'] != manifest or dataset_from_records(rebuilt['records']).canonical_bytes != dataset.canonical_bytes:
        fail('generation_manifest', 'GENERATION_PROVENANCE_MISMATCH')
    return manifest


def reviewed_records(dataset, receipt):
    obj(receipt, ('dataset_hash', 'reviewer', 'reviewed_at', 'approved_qids'), ('dataset_hash', 'reviewer', 'reviewed_at', 'approved_qids'))
    text(receipt['reviewer'], 'reviewer')
    from datetime import datetime
    try:
        stamp = receipt['reviewed_at']
        if type(stamp) is not str or not stamp.endswith('Z') or 'T' not in stamp:
            raise ValueError
        datetime.fromisoformat(stamp[:-1] + '+00:00')
    except (ValueError, TypeError):
        fail('reviewed_at', 'INVALID_UTC_TIMESTAMP')
    if receipt['dataset_hash'] != dataset.dataset_hash or set(ids(receipt['approved_qids'], 'approved_qids')) != {r.qid for r in dataset.records}:
        fail('review', 'EXACT_REVIEW_COVERAGE_REQUIRED')
    result = []
    for record in dataset.records:
        payload = record.to_dict()
        notes = generation_notes(record)
        if notes is None or notes.get('generation_method') != METHOD or notes.get('generation_version') != VERSION:
            fail('review', 'GENERATION_PROVENANCE_REQUIRED')
        notes.update(review_status='APPROVED', human_reviewed=True, review_receipt=receipt, reviewer_identity_verified=False)
        payload.update(notes=canonical_line(notes).decode().strip(), tags=[t for t in record.tags if t != 'NO_HUMAN_REVIEW'] + ['HUMAN_REVIEW_RECEIPT'])
        result.append(payload)
    return result


def generation_notes(record):
    try:
        notes = strict_json(record.notes) if record.notes is not None else None
    except (ValueError, TypeError):
        notes = None
    return notes if type(notes) is dict and ('generation_method' in notes or 'generation_version' in notes) else None
