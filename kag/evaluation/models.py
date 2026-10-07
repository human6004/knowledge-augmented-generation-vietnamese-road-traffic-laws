"""Strict immutable authoring models. No SDK initialization or provider access."""
from dataclasses import asdict, dataclass, field
from datetime import date
import math
import re
import unicodedata

CATEGORIES = ('definition', 'obligation', 'sanction_numeric', 'effectiveness_metadata',
              'inter_document', 'multi_hop', 'unanswerable', 'traffic_sign')


@dataclass(frozen=True)
class ValidationIssue:
    path: str = ''
    line: int = 0
    qid: str | None = None
    field: str = ''
    code: str = 'INVALID'


class ValidationError(ValueError):
    def __init__(self, issues):
        self.issues = tuple(issues)
        super().__init__('; '.join(i.code + ':' + i.field for i in self.issues))


def fail(name, code='INVALID_TYPE'):
    raise ValidationError((ValidationIssue(field=name, code=code),))


def obj(value, allowed, required=()):
    if type(value) is not dict:
        fail('', 'OBJECT_REQUIRED')
    for name in value:
        if name not in allowed:
            fail(str(name), 'UNKNOWN_KEY')
    for name in required:
        if name not in value or value[name] is None:
            fail(name, 'REQUIRED')


def text(value, name, *, identity=False, blank=False):
    if type(value) is not str or (not blank and not value.strip()):
        fail(name)
    try:
        value.encode('utf-8', errors='strict')
    except UnicodeError:
        fail(name, 'INVALID_UNICODE')
    if identity and (value != value.strip() or any(unicodedata.category(c) == 'Cc' for c in value)):
        fail(name, 'INVALID_ID')
    return value


def ids(value, name, *, identity=True):
    if type(value) is not list:
        fail(name)
    result = tuple(text(v, name, identity=identity) for v in value)
    if len(set(result)) != len(result):
        fail(name, 'DUPLICATE')
    return result


def boolean(value, name):
    if type(value) is not bool:
        fail(name)
    return value


def calendar(value):
    if value is None:
        return None
    if type(value) is not str or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        fail('as_of', 'INVALID_DATE')
    try:
        date.fromisoformat(value)
    except ValueError:
        fail('as_of', 'INVALID_DATE')
    return value


@dataclass(frozen=True)
class CitationGold:
    doc_id: str
    unit_id: str | None = None
    sign_id: str | None = None
    required: bool = True
    field: str | None = None
    start: int | None = None
    end: int | None = None
    quote: str | None = None

    @classmethod
    def from_dict(cls, value):
        obj(value, cls.__dataclass_fields__, ('doc_id',))
        result = dict(doc_id=text(value['doc_id'], 'doc_id', identity=True))
        for name in ('unit_id', 'sign_id'):
            result[name] = None if value.get(name) is None else text(value[name], name, identity=True)
        result['required'] = boolean(value.get('required', True), 'required')
        span = [value.get(k) for k in ('field', 'start', 'end', 'quote')]
        if any(v is not None for v in span):
            if any(v is None for v in span):
                fail('citation_gold', 'INCOMPLETE_SPAN')
            field_name, start, end, quote = span
            fields = ('moTa','ten') if result['sign_id'] else ('text',) if result['unit_id'] else ('title',)
            if field_name not in fields:
                fail('field', 'INCOMPATIBLE_FIELD')
            if type(start) is not int or type(end) is not int or not 0 <= start < end:
                fail('start', 'INVALID_SPAN')
            text(quote, 'quote', blank=True)
            if len(quote) != end - start:
                fail('quote', 'INVALID_SPAN')
            result.update(zip(('field','start','end','quote'),span))
        return cls(**result)

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class LegacyReference:
    document_id: str
    text: str
    article: str | None = None
    clause: str | None = None
    point: str | None = None
    required: bool = True

    @classmethod
    def from_dict(cls, value):
        obj(value, cls.__dataclass_fields__, ('document_id','text'))
        result = {name:text(value[name], name) for name in ('document_id','text')}
        for name in ('article','clause','point'):
            result[name] = None if value.get(name) is None else text(value[name],name,blank=True)
        result['required'] = boolean(value.get('required',True),'required')
        return cls(**result)

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class AnswerReference:
    expected_answer: str | None = None
    accepted_facts: tuple[str,...] = ()
    markers: tuple[str,...] = ()

    @classmethod
    def from_dict(cls, value):
        obj(value, cls.__dataclass_fields__)
        answer = value.get('expected_answer')
        if answer is not None:
            text(answer,'expected_answer')
        return cls(answer, ids(value.get('accepted_facts',[]),'accepted_facts',identity=False),
                   ids(value.get('markers',[]),'markers',identity=False))

    def to_dict(self):
        return dict(expected_answer=self.expected_answer, accepted_facts=list(self.accepted_facts),markers=list(self.markers))


@dataclass(frozen=True)
class EvaluationRecord:
    schema_version: str
    dataset_version: str
    dataset_status: str
    qid: str
    question: str
    category: str
    expected_abstain: bool
    as_of: str | None = None
    gold_doc_ids: tuple[str,...] = ()
    gold_unit_ids: tuple[str,...] = ()
    gold_sign_ids: tuple[str,...] = ()
    answer_reference: AnswerReference | None = None
    citation_gold: tuple[CitationGold,...] = ()
    legacy_references: tuple[LegacyReference,...] = ()
    source_group: str | None = None
    notes: str | None = None
    tags: tuple[str,...] = ()

    @classmethod
    def from_dict(cls, value):
        required = ('schema_version','dataset_version','dataset_status','qid','question','category','expected_abstain')
        obj(value,cls.__dataclass_fields__,required)
        if value['schema_version'] != '1.0':
            fail('schema_version','UNSUPPORTED_SCHEMA')
        if value['dataset_status'] not in ('PROVISIONAL','FROZEN'):
            fail('dataset_status','INVALID_STATUS')
        if value['category'] not in CATEGORIES:
            fail('category','INVALID_CATEGORY')
        result = {k:value[k] for k in required}
        for name in ('dataset_version','qid'):
            text(result[name],name,identity=True)
        text(result['question'],'question')
        boolean(result['expected_abstain'],'expected_abstain')
        result['as_of'] = calendar(value.get('as_of'))
        for name in ('gold_doc_ids','gold_unit_ids','gold_sign_ids','tags'):
            result[name] = ids(value.get(name,[]),name,identity=name != 'tags')
        for name in ('source_group','notes'):
            result[name] = value.get(name)
            if result[name] is not None:
                text(result[name],name,blank=True)
        result['answer_reference'] = None if value.get('answer_reference') is None else AnswerReference.from_dict(value['answer_reference'])
        for name, model in (('citation_gold',CitationGold),('legacy_references',LegacyReference)):
            raw = value.get(name,[])
            if type(raw) is not list:
                fail(name)
            result[name] = tuple(model.from_dict(v) for v in raw)
        keys = [tuple(v for k,v in c.to_dict().items() if k != 'required') for c in result['citation_gold']]
        if len(set(keys)) != len(keys):
            fail('citation_gold','DUPLICATE')
        if len(set(result['legacy_references'])) != len(result['legacy_references']):
            fail('legacy_references','DUPLICATE')
        return cls(**result)

    def to_dict(self):
        result = asdict(self)
        for name in ('gold_doc_ids','gold_unit_ids','gold_sign_ids','tags'):
            result[name] = list(getattr(self,name))
        result['citation_gold'] = [g.to_dict() for g in self.citation_gold]
        result['legacy_references'] = [g.to_dict() for g in self.legacy_references]
        result['answer_reference'] = self.answer_reference.to_dict() if self.answer_reference else None
        return result


@dataclass(frozen=True)
class JudgeConfig:
    name: str
    version: str = ''
    model: str = ''
    prompt_version: str = ''
    temperature: float = 0.0
    seed: int | None = None
    calibrated: bool = False

    @classmethod
    def from_dict(cls, value):
        obj(value,cls.__dataclass_fields__,('name',))
        text(value['name'],'name')
        for name in ('version','model','prompt_version'):
            text(value.get(name,''),name,blank=True)
        temp = value.get('temperature',0.0)
        if type(temp) not in (int,float) or not math.isfinite(temp):
            fail('temperature')
        seed = value.get('seed')
        if seed is not None and type(seed) is not int:
            fail('seed')
        boolean(value.get('calibrated',False),'calibrated')
        return cls(**dict(value,temperature=float(temp)))


@dataclass(frozen=True)
class EvaluationProtocol:
    protocol_version: str = '1.0'
    eval_version: str = '1.0'
    metric_policy_version: str = '1.0'
    ks: tuple[int,...] = (1,5,10)
    top_k: int = 10
    expand: bool = False
    rank_semantics: str = 'channel_projected_returned_top_k'
    identity_catalog_hash: str | None = None
    release_id: str | None = None
    judge_config: JudgeConfig | None = None

    def __post_init__(self):
        if type(self.ks) not in (tuple,list) or not self.ks or any(type(k) is not int or k <= 0 for k in self.ks) or len(set(self.ks)) != len(self.ks):
            fail('ks','INVALID_CUTOFF')
        if type(self.top_k) is not int or self.top_k < max(self.ks):
            fail('top_k','INVALID_CUTOFF')
        object.__setattr__(self,'ks',tuple(sorted(self.ks)))
        for name in ('protocol_version','eval_version','metric_policy_version'):
            if getattr(self,name) != '1.0':
                fail(name,'UNSUPPORTED_VERSION')
        if self.expand is not False or self.rank_semantics != 'channel_projected_returned_top_k':
            fail('rank_semantics','INVALID_RANK_POLICY')
        if self.identity_catalog_hash is not None and (type(self.identity_catalog_hash) is not str or not re.fullmatch('[0-9a-f]{64}',self.identity_catalog_hash)):
            fail('identity_catalog_hash')
        if self.release_id is not None:
            text(self.release_id,'release_id',identity=True)
        if self.judge_config is not None:
            raw = asdict(self.judge_config) if isinstance(self.judge_config,JudgeConfig) else self.judge_config
            object.__setattr__(self,'judge_config',JudgeConfig.from_dict(raw))

    @classmethod
    def from_dict(cls, value):
        obj(value,cls.__dataclass_fields__)
        return cls(**value)

    def to_dict(self):
        result = asdict(self)
        result['ks'] = list(self.ks)
        return result

    @property
    def protocol_hash(self):
        from .dataset import canonical_protocol_bytes, sha256
        return sha256(canonical_protocol_bytes(self))


@dataclass(frozen=True)
class ValidatedDataset:
    records: tuple[EvaluationRecord,...]
    source_sha256: str | None
    dataset_hash: str
    canonical_bytes: bytes
    official_benchmark: bool = False
    manifest_verified: bool = False


@dataclass(frozen=True)
class MetricValue:
    value: float | None = None
    status: str = 'UNAVAILABLE'
    numerator: float | None = None
    denominator: float | None = None
    reason: str | None = None

    def to_dict(self):
        return asdict(self)


@dataclass
class QuestionResult:
    qid: str
    category: str
    source_group: str | None = None
    status: str = 'INELIGIBLE'
    metrics: dict = field(default_factory=dict)
    eligibility: dict = field(default_factory=dict)
    reasons: list = field(default_factory=list)
    retrieval: dict | None = None
    answer_result: dict | None = None
    latency_ms: float | None = None
    error: dict | None = None
    cost: None = None
    usage: None = None

    def to_dict(self):
        result = asdict(self)
        result['metrics'] = {k:v.to_dict() for k,v in self.metrics.items()}
        return result


@dataclass
class RunContext:
    output_dir: object
    dataset: ValidatedDataset
    protocol: EvaluationProtocol
    mode: str
    manifest: dict
    manifest_bytes: bytes


@dataclass
class EvaluationRun:
    context: RunContext
    rows: tuple[QuestionResult,...]
    status: str = 'RUNNING'
