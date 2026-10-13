"""Explicit legacy-to-PROVISIONAL conversion. Never execute legacy code or infer IDs."""
from .dataset import canonical_line, sha256, validate_catalog
from .models import (CATEGORIES, CitationGold, EvaluationRecord, LegacyReference, ValidationError,
                     boolean, calendar, fail, ids, obj, text)

LEGACY_KEYS = {'id','question','category','answerable','gold_evidence','gold_markers','source_id','origin',
               'notes','verification_status','legacy_id','candidate_id','fix_action','gold_claims','source_name','source_url'}


def _mapping(bundle, catalog):
    if bundle is None:
        if catalog is not None:
            fail('mapping','MAPPING_REQUIRED')
        return {}
    obj(bundle,('schema_version','current_catalog_hash','entries'),('schema_version','current_catalog_hash','entries'))
    if bundle['schema_version'] != '1.0' or catalog is None:
        fail('mapping','CATALOG_REQUIRED')
    identities = validate_catalog(catalog)
    if sha256(canonical_line(catalog)) != bundle['current_catalog_hash']:
        fail('mapping','STALE_MAPPING')
    if type(bundle['entries']) is not list:
        fail('entries')
    result = {}
    for entry in bundle['entries']:
        obj(entry,('legacy_reference','citation'),('legacy_reference','citation'))
        ref = LegacyReference.from_dict(entry['legacy_reference'])
        citation = CitationGold.from_dict(entry['citation'])
        if citation.required != ref.required:
            fail('required','MAPPING_REQUIRED_MISMATCH')
        for value,channel in ((citation.doc_id,'document'),(citation.unit_id,'unit'),(citation.sign_id,'sign')):
            if value is not None and value not in identities[channel]:
                fail(channel,'MAPPING_OUTSIDE_CATALOG')
        key = canonical_line(ref.to_dict())
        if key in result:
            fail('entries','AMBIGUOUS_MAPPING')
        result[key] = citation.to_dict()
    return result


def _placeholder(value):
    return type(value) is str and value.strip().upper() in ('PENDING','TODO','TBD','UNKNOWN','PLACEHOLDER')


def import_legacy(payload, *, dataset_version, as_of=None, mapping=None, current_catalog=None):
    text(dataset_version,'dataset_version',identity=True)
    calendar(as_of)
    mapped = _mapping(mapping,current_catalog)
    if type(payload) is not list:
        fail('payload','LEGACY_LIST_REQUIRED')
    canonical_line(payload)
    result = dict(converted=[],rejected=[],needs_manual_mapping=[],record_provenance=[],provenance={
        'input_canonical_sha256':sha256(canonical_line(payload)),
        'mapping_sha256':sha256(canonical_line(mapping)) if mapping is not None else None,
        'current_catalog_hash':sha256(canonical_line(current_catalog)) if current_catalog is not None else None,
        'dataset_status':'PROVISIONAL','official_benchmark':False,'paper_eligible':False,
        'as_of':as_of,'dataset_version':dataset_version})
    seen = set()
    for index,value in enumerate(payload):
        diagnostic = dict(index=index,legacy_id=None,legacy_references=[],reasons=[],ignored_fields=[])
        provenance = dict(index=index,legacy_id=None,provenance={},legacy_evidence_ids=[],source_url=None)
        result['record_provenance'].append(provenance)
        try:
            if type(value) is not dict:
                fail('record','OBJECT_REQUIRED')
            if 'input' in value and 'question' not in value:
                diagnostic['reasons'] = ['LEGACY_AUTHORING_FIELDS_MISSING']
                diagnostic['ignored_fields'] = sorted(value)
                result['needs_manual_mapping'].append(diagnostic)
                continue
            obj(value,LEGACY_KEYS)
            for name in ('origin','candidate_id','legacy_id','fix_action','verification_status'):
                if name in value:
                    if value[name] is not None:
                        text(value[name],name,blank=True)
                    provenance['provenance'][name] = value[name]
            if value.get('source_url') is not None:
                provenance['source_url'] = text(value['source_url'],'source_url',blank=True)
            if _placeholder(value.get('verification_status')):
                fail('verification_status','PLACEHOLDER_GOLD')
            if not all(k in value for k in ('id','question','category','answerable','gold_evidence')):
                diagnostic['reasons'] = ['LEGACY_AUTHORING_FIELDS_MISSING']
                result['needs_manual_mapping'].append(diagnostic)
                continue
            qid = text(value['id'],'id',identity=True)
            diagnostic['legacy_id'] = qid
            provenance['legacy_id'] = qid
            if qid in seen:
                fail('id','DUPLICATE_QID')
            seen.add(qid)
            text(value['question'],'question')
            if value['category'] not in CATEGORIES:
                fail('category','INVALID_CATEGORY')
            answerable = boolean(value['answerable'],'answerable')
            refs = value['gold_evidence']
            if type(refs) is not list:
                fail('gold_evidence')
            references = []
            for ref in refs:
                obj(ref,(*LegacyReference.__dataclass_fields__,'evidence_id'),('document_id','text'))
                label = ref.get('evidence_id')
                if label is not None:
                    text(label,'evidence_id')
                provenance['legacy_evidence_ids'].append(label)
                references.append(LegacyReference.from_dict({k:v for k,v in ref.items() if k != 'evidence_id'}).to_dict())
            if any(_placeholder(ref[k]) for ref in references for k in ('document_id','text')):
                fail('gold_evidence','PLACEHOLDER_GOLD')
            diagnostic['legacy_references'] = references
            markers = ids(value.get('gold_markers',[]),'gold_markers',identity=False)
            claims = ids(value.get('gold_claims',[]),'gold_claims',identity=False)
            if any(_placeholder(m) for m in (*markers,*claims)):
                fail('gold_markers','PLACEHOLDER_GOLD')
            if answerable and not references:
                fail('gold_evidence','MISSING_GOLD')
            if as_of is None:
                diagnostic['reasons'].append('AS_OF_REQUIRED')
            citations = []
            for ref in references:
                target = mapped.get(canonical_line(ref))
                if target is None:
                    diagnostic['reasons'].append('UNMAPPED_REFERENCE')
                else:
                    citations.append(target)
            distinct = {}
            for citation in citations:
                key = canonical_line({k:v for k,v in citation.items() if k != 'required'})
                if key in distinct:
                    distinct[key]['required'] |= citation['required']
                else:
                    distinct[key] = dict(citation)
            citations = list(distinct.values())
            diagnostic['reasons'] = list(dict.fromkeys(diagnostic['reasons']))
            diagnostic['ignored_fields'] = sorted(set(value)-{'id','question','category','answerable','gold_evidence','gold_markers','notes','source_id'})
            if diagnostic['reasons']:
                result['needs_manual_mapping'].append(diagnostic)
                continue
            # Keep mapping depth exact. A sign anchor is not a retrieved LegalUnit target.
            converted = dict(schema_version='1.0',dataset_version=dataset_version,dataset_status='PROVISIONAL',
                             qid=qid,question=value['question'],category=value['category'],expected_abstain=not answerable,
                             as_of=as_of,legacy_references=references,citation_gold=citations,
                             gold_doc_ids=list(dict.fromkeys(c['doc_id'] for c in citations)),
                             gold_unit_ids=list(dict.fromkeys(c['unit_id'] for c in citations if c['unit_id'] is not None and c['sign_id'] is None)),
                             gold_sign_ids=list(dict.fromkeys(c['sign_id'] for c in citations if c['sign_id'] is not None)),
                             answer_reference={'markers':list(markers),'accepted_facts':list(claims)} if markers or claims else None,
                             source_group=value.get('source_id',value.get('source_name')),notes=value.get('notes'))
            result['converted'].append(EvaluationRecord.from_dict(converted).to_dict())
        except ValidationError as exc:
            diagnostic['reasons'] = list(dict.fromkeys(i.code for i in exc.issues))
            result['rejected'].append(diagnostic)
    result['counts'] = {name:len(result[name]) for name in ('converted','rejected','needs_manual_mapping')}
    result['counts']['requested'] = len(payload)
    return result
