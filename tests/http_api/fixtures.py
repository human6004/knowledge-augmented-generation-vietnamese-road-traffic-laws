"""Synthetic native results and future internal verified-source certificates."""
from dataclasses import dataclass
import hashlib

from kag.bootstrap import initialize
initialize()
from kag.builder.codec import canonical_json
from kag.legal_solver import AnswerResult, Citation

SCHEMA = {'namespace': 'VietRoadTraffic', 'schema_sha256': 'a' * 64,
          'contract_sha256': 'b' * 64}
USER = '00000000-0000-4000-8000-000000000001'


def query(**changes):
    return dict(user_id=USER, message=' Câu hỏi e\u0301 😀 ', context_id='',
                schema_contract=dict(SCHEMA), **changes) if not changes else {
                    **query(), **changes}


@dataclass(frozen=True)
class VerifiedSource:
    citation: Citation
    entity_type: str
    entity_id: str
    source_text: str
    java_eligible: bool = True


@dataclass(frozen=True)
class VerifiedSources:
    citations: tuple[VerifiedSource, ...]


def source(kind='LegalUnit', identity='unit-1', field='text', text='Nguồn e\u0301 😀.',
           doc_id='document-1', unit_id='unit-1', sign_id=None, java_eligible=True):
    entity_type = 'VietRoadTraffic.' + kind
    evidence_id = hashlib.sha256(canonical_json([entity_type, identity, field]).encode()).hexdigest()
    citation = Citation(doc_id, unit_id, sign_id, evidence_id, field, 0, len(text), text)
    return VerifiedSource(citation, entity_type, identity, text, java_eligible)


def answered(*sources, answer=None):
    sources = sources or (source(),)
    citations = tuple(s.citation for s in sources)
    result = AnswerResult(answer if answer is not None else
                          'Căn cứ nguồn đã xác nhận:\n' + '\n\n'.join(c.quote for c in citations),
                          citations, False)
    return result, VerifiedSources(tuple(sources))


def sign():
    return source('TrafficSign', 'sign-1', 'moTa', unit_id=None, sign_id='sign-1')


def metadata():
    return source('LegalDocument', 'document-1', 'effective_from', '2020-01-01', unit_id=None)
