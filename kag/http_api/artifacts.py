"""Operator-sealed immutable evidence; no runtime construction or HTTP routes.

The root and selected release are trusted configuration, never request inputs.
Hashes establish integrity within that trust boundary, not independent live proof.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from kag.builder.codec import canonical_json, decode_properties
from kag.vector_contract import TARGETS
from .contract import ApiFailure, SchemaIdentity, _json_value, _text

if TYPE_CHECKING:
    from kag.legal_solver import AnswerResult, Citation


class VerificationState(str, Enum):
    VERIFIED = 'verified'
    UNAVAILABLE = 'unavailable'
    INVALID = 'invalid'
    UNVERIFIED = 'unverified'


class ArtifactFailure(ApiFailure):
    """Internal state supplements fixed public errors; no raw cause details."""
    def __init__(self, state: VerificationState, code='NOT_READY'):
        self.state = state
        super().__init__(code)


def _invalid(code='NOT_READY'):
    raise ArtifactFailure(VerificationState.INVALID, code)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _freeze(value):
    if type(value) is dict:
        return MappingProxyType({k:_freeze(v) for k,v in value.items()})
    if type(value) is list:
        return tuple(_freeze(v) for v in value)
    return value


def _keys(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        _invalid()


def _identity(value):
    if not _text(value) or not value.strip() or len(value.encode('utf-8')) > 512:
        _invalid()
    return value


def _date(value):
    if not _text(value) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        _invalid()
    return date.fromisoformat(value)


def _json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                _invalid()
            value[key] = item
        return value

    def constant(value):
        _invalid()

    value = json.loads(raw.decode('utf-8', errors='strict'), object_pairs_hook=pairs,
                       parse_constant=constant)
    _json_value(value)
    return value


def _read(root, filename):
    # Reject symlinks at every component, including the operator's root.
    root = root.absolute()
    path = root/filename
    if any(p.is_symlink() for p in (path, root, *root.parents)):
        _invalid()
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 64*1024*1024:
            _invalid()
        raw = stream.read(64*1024*1024+1)
    if len(raw) > 64*1024*1024:
        _invalid()
    return raw


_BINDING = ('release_id','schema_contract','source_snapshot_id','graph_fingerprint',
            'database_id','server_id','database','namespace')
_FILES = {'source_catalog_sha256':'source-catalog.json', 'graph_receipt_sha256':'graph-receipt.json',
    'backend_receipt_sha256':'backend-receipt.json',
    'serving_authority_receipt_sha256':'serving-authority.json',
    'webapp_publication_sha256':'webapp-publication.json'}


@dataclass(frozen=True)
class SourceRecord:
    entity_type: str
    entity_id: str
    doc_id: str
    unit_id: str | None
    sign_id: str | None
    field: str
    physical_field: str
    source_text: str
    source_sha256: str
    metadata: MappingProxyType
    graph_context: tuple

    @property
    def evidence_id(self):
        return _sha(canonical_json([self.entity_type,self.entity_id,self.field]).encode('utf-8'))


@dataclass(frozen=True)
class ServingRelease:
    root: Path
    release_id: str
    release_kind: str
    schema_contract: SchemaIdentity
    descriptor_sha256: str
    descriptor: MappingProxyType
    records: tuple[SourceRecord, ...]
    artifacts: tuple[tuple[str, bytes], ...]
    contract_bytes: bytes
    backend: MappingProxyType
    publication: MappingProxyType | None


@dataclass(frozen=True)
class VerifiedSource:
    citation: Citation
    entity_type: str
    entity_id: str
    source_text: str
    java_eligible: bool
    source_sha256: str
    physical_field: str


@dataclass(frozen=True)
class VerifiedSources:
    citations: tuple[VerifiedSource, ...]
    release_id: str
    source_snapshot_id: str
    schema_contract: SchemaIdentity
    release_descriptor_sha256: str
    as_of: date
    webapp_snapshot_id: str | None
    publication_state: VerificationState
    state: VerificationState = VerificationState.VERIFIED


def _binding(receipt, descriptor):
    if any(receipt.get(key) != descriptor[key] for key in _BINDING):
        _invalid()


def _endpoint(value):
    parsed = urlsplit(value)
    if (parsed.scheme not in ('http','https') or not parsed.hostname or not parsed.port
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ('','/') or value.strip() != value):
        _invalid()


def _catalog(value, descriptor, contract):
    _keys(value, ('schema',*_BINDING,'records'))
    _binding(value,descriptor)
    if value['schema'] != 'h1-source-catalog-1.0' or type(value['records']) is not list:
        _invalid()
    records, seen, entities = [], set(), {}
    for entry in value['records']:
        _keys(entry, SourceRecord.__dataclass_fields__)
        kind = entry['entity_type'].removeprefix(descriptor['namespace']+'.')
        if kind not in TARGETS or entry['entity_type'] != descriptor['namespace']+'.'+kind:
            _invalid()
        for field in ('entity_id','doc_id','field','physical_field'):
            _identity(entry[field])
        for field in ('unit_id','sign_id'):
            if entry[field] is not None:
                _identity(entry[field])
        rows = contract['node_properties'][kind]
        metadata = entry['metadata']
        if type(metadata) is not dict or set(metadata) - {r['logical_name'] for r in rows}:
            _invalid()
        physical = {r['schema_name']:canonical_json(metadata[r['logical_name']])
            if r['contract_type'] == 'JSON_TEXT' else metadata[r['logical_name']]
            for r in rows if r['logical_name'] in metadata}
        decoded = decode_properties(physical,rows)
        if (decoded != metadata or decoded['id'] != entry['entity_id'] or decoded['name'] != decoded['id']
                or kind == 'LegalUnit' and decoded.get('unit_type') not in contract['unit_type_values']):
            _invalid()
        expected = (decoded['id'],None,None) if kind == 'LegalDocument' else (
            decoded['doc_id'], decoded['id'] if kind == 'LegalUnit' else decoded.get('unit_id'),
            decoded['id'] if kind == 'TrafficSign' else None)
        if (entry['doc_id'],entry['unit_id'],entry['sign_id']) != expected:
            _invalid()
        row = next((r for r in rows if r['schema_name'] == entry['physical_field']), None)
        if (row is None or entry['field'] not in (row['logical_name'],row['schema_name'])
                or not _text(entry['source_text']) or not entry['source_text']
                or metadata.get(row['logical_name']) != entry['source_text']
                or _sha(entry['source_text'].encode('utf-8')) != entry['source_sha256']):
            _invalid()
        if type(entry['graph_context']) is not list:
            _invalid()
        relation_keys = set()
        for relation in entry['graph_context']:
            _keys(relation, ('from','predicate','to','properties'))
            rule = contract['relations'].get(relation['predicate'])
            if not rule or any(type(relation[s]) is not list or len(relation[s]) != 2 for s in ('from','to')):
                _invalid()
            for side in ('from','to'):
                _identity(relation[side][1])
                if relation[side][0] != descriptor['namespace']+'.'+rule[side+'_type']:
                    _invalid()
            if [entry['entity_type'],entry['entity_id']] not in (relation['from'],relation['to']):
                _invalid()
            if type(relation['properties']) is not dict:
                _invalid()
            relation_key = (*relation['from'],relation['predicate'],*relation['to'])
            if relation_key in relation_keys:
                _invalid()
            relation_keys.add(relation_key)
            relation_rows = contract['relation_properties'][relation['predicate']]
            if set(relation['properties']) - {r['logical_name'] for r in relation_rows}:
                _invalid()
            encoded = {r['schema_name']:canonical_json(relation['properties'][r['logical_name']])
                if r['contract_type'] == 'JSON_TEXT' else relation['properties'][r['logical_name']]
                for r in relation_rows if r['logical_name'] in relation['properties']}
            if decode_properties(encoded,relation_rows) != relation['properties']:
                _invalid()
        record = SourceRecord(**{**entry,'metadata':_freeze(metadata),
                                 'graph_context':_freeze(entry['graph_context'])})
        if record.evidence_id in seen:
            _invalid()
        seen.add(record.evidence_id)
        key = record.entity_type,record.entity_id
        identity = record.metadata,record.graph_context
        if key in entities and entities[key] != identity:
            _invalid()
        entities[key] = identity
        records.append(record)
    for record in records:
        if (descriptor['namespace']+'.LegalDocument',record.doc_id) not in entities:
            _invalid()
        linked_unit = record.unit_id if record.sign_id else record.metadata.get('parent_id')
        if linked_unit:
            unit = entities.get((descriptor['namespace']+'.LegalUnit',linked_unit))
            if unit is None or unit[0].get('doc_id') != record.doc_id:
                _invalid()
        for relation in record.graph_context:
            if any(tuple(relation[s]) not in entities for s in ('from','to')):
                _invalid()
    return tuple(records)


def _publication(value, descriptor, records):
    if value is None:
        return None
    _keys(value, ('schema','snapshot_id','schema_contract','source_snapshot_id','as_of',
                  'timezone','documents','units'))
    if (value['schema'] != 'h1-webapp-publication-1.0' or value['timezone'] != 'Asia/Saigon'
            or value['snapshot_id'] != descriptor['webapp_snapshot_id']
            or value['schema_contract'] != descriptor['schema_contract']
            or value['source_snapshot_id'] != descriptor['source_snapshot_id']):
        _invalid()
    _date(value['as_of'])
    documents = {r.entity_id:r for r in records if r.entity_type.endswith('.LegalDocument')}
    units = {r.entity_id:r for r in records if r.entity_type.endswith('.LegalUnit') and r.field == 'text'}
    for group in ('documents','units'):
        if type(value[group]) is not list:
            _invalid()
        seen = set()
        for entry in value[group]:
            fields = ('doc_id','published','version','effective_from','effective_to',
                'current_effective','replaces_eligible') if group == 'documents' else (
                'doc_id','unit_id','text_sha256','published','version')
            _keys(entry,fields)
            key = entry['doc_id'] if group == 'documents' else entry['unit_id']
            _identity(key)
            _identity(entry['version'])
            if key in seen or type(entry['published']) is not bool:
                _invalid()
            seen.add(key)
            record = (documents if group == 'documents' else units).get(key)
            if record is None or record.doc_id != entry['doc_id']:
                _invalid()
            if group == 'units':
                if entry['text_sha256'] != record.source_sha256:
                    _invalid()
            else:
                for field in ('current_effective','replaces_eligible'):
                    if type(entry[field]) is not bool:
                        _invalid()
                for field in ('effective_from','effective_to'):
                    if entry[field] != record.metadata.get(field):
                        _invalid()
                    if entry[field] is not None:
                        _date(entry[field])
    return _freeze(value)


def load_release(root: Path, expected_release_id: str) -> ServingRelease:
    """Load one operator-selected snapshot; never claim a live verified backend."""
    try:
        if not isinstance(root,Path):
            _invalid()
        _identity(expected_release_id)
        raw = _read(root,'release.json')
        descriptor = _json(raw)
        _keys(descriptor, ('schema',*_BINDING,'release_kind',*_FILES,'serving_mode','sealed_at','webapp_snapshot_id'))
        if descriptor['schema'] != 'h1-release-1.0' or descriptor['release_id'] != expected_release_id:
            _invalid()
        for field in (*_BINDING,'release_kind'):
            if field != 'schema_contract':
                _identity(descriptor[field])
        if not re.fullmatch(r'[0-9a-f]{64}',descriptor['graph_fingerprint']):
            _invalid()
        schema_root = Path(__file__).resolve().parents[1]/'schema'
        schema_bytes = _read(schema_root,'VietRoadTraffic.schema')
        contract_bytes = _read(schema_root,'schema_contract.json')
        contract = _json(contract_bytes)
        identity = SchemaIdentity(contract['namespace'],_sha(schema_bytes),_sha(contract_bytes))
        if (descriptor['schema_contract'] != identity.__dict__ or descriptor['namespace'] != identity.namespace
                or contract['runtime_contract']['schema_sha256'] != identity.schema_sha256):
            _invalid()
        if descriptor['serving_mode'] != 'sealed_read_only':
            raise ArtifactFailure(VerificationState.UNVERIFIED)
        if not _text(descriptor['sealed_at']) or not re.fullmatch(
                r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z',descriptor['sealed_at']):
            _invalid()
        datetime.fromisoformat(descriptor['sealed_at'].replace('Z','+00:00'))
        if (descriptor['webapp_snapshot_id'] is None) != (descriptor['webapp_publication_sha256'] is None):
            _invalid()
        loaded, artifacts = {}, [('release.json',raw)]
        for field, filename in _FILES.items():
            expected = descriptor[field]
            if field == 'webapp_publication_sha256' and expected is None:
                continue
            if not _text(expected) or not re.fullmatch(r'[0-9a-f]{64}',expected):
                _invalid()
            data = _read(root,filename)
            if _sha(data) != expected:
                _invalid()
            loaded[filename] = _json(data)
            artifacts.append((filename,data))
        graph, backend, authority = [loaded[n] for n in
            ('graph-receipt.json','backend-receipt.json','serving-authority.json')]
        _keys(graph, ('schema',*_BINDING,'graph_verified','source_catalog_sha256'))
        _keys(backend, ('schema',*_BINDING,'reader_endpoint','project_id','identity_attested'))
        _keys(authority, ('schema',*_BINDING,'reader_endpoint','project_id','graph_frozen','schema_frozen',
            'read_only','catalog_complete','source_catalog_sha256','backend_receipt_sha256'))
        for receipt, schema in ((graph,'h1-graph-receipt-1.0'),(backend,'h1-backend-receipt-1.0'),
                               (authority,'h1-serving-authority-1.0')):
            if receipt['schema'] != schema:
                _invalid()
            _binding(receipt,descriptor)
        if (graph['source_catalog_sha256'] != descriptor['source_catalog_sha256']
                or authority['source_catalog_sha256'] != descriptor['source_catalog_sha256']
                or authority['backend_receipt_sha256'] != descriptor['backend_receipt_sha256']
                or authority['reader_endpoint'] != backend['reader_endpoint']
                or authority['project_id'] != backend['project_id']):
            _invalid()
        _endpoint(backend['reader_endpoint'])
        _identity(backend['project_id'])
        if (graph['graph_verified'] is not True or backend['identity_attested'] is not True
                or any(authority[k] is not True for k in ('graph_frozen','schema_frozen','read_only','catalog_complete'))):
            raise ArtifactFailure(VerificationState.UNVERIFIED)
        records = _catalog(loaded['source-catalog.json'],descriptor,contract)
        publication = _publication(loaded.get('webapp-publication.json'),descriptor,records)
        return ServingRelease(root.absolute(),expected_release_id,descriptor['release_kind'],identity,
            _sha(raw),_freeze(descriptor),records,tuple(artifacts),contract_bytes,_freeze(backend),publication)
    except ArtifactFailure:
        raise
    except OSError:
        raise ArtifactFailure(VerificationState.UNAVAILABLE) from None
    except ApiFailure:
        raise ArtifactFailure(VerificationState.INVALID) from None
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError):
        raise ArtifactFailure(VerificationState.INVALID) from None


def _unchanged(release):
    if any(_read(release.root,name) != raw for name,raw in release.artifacts):
        _invalid()
    schema_root = Path(__file__).resolve().parents[1]/'schema'
    if (_read(schema_root,'schema_contract.json') != release.contract_bytes
            or _sha(_read(schema_root,'VietRoadTraffic.schema')) != release.schema_contract.schema_sha256):
        _invalid()


def _backend(reader, release):
    try:
        metadata = reader.database_metadata()
        indexes = reader.indexes()
    except Exception:
        raise ArtifactFailure(VerificationState.UNAVAILABLE) from None
    descriptor = release.descriptor
    expected = {'name':descriptor['database'],'databaseID':descriptor['database_id'],
                'serverID':descriptor['server_id'],'currentStatus':'online'}
    if (metadata != expected or getattr(reader,'database',None) != descriptor['database']
            or getattr(reader,'endpoint',None) != release.backend['reader_endpoint']):
        _invalid('SOURCE_VALIDATION_FAILED')
    if type(indexes) is not list:
        _invalid('SOURCE_VALIDATION_FAILED')
    for kind, targets in TARGETS.items():
        for _, field in targets:
            found = [i for i in indexes if i.get('type') == 'VECTOR'
                and i.get('labelsOrTypes') == [descriptor['namespace']+'.'+kind]
                and i.get('properties') == [field]]
            if len(found) != 1:
                _invalid('SOURCE_VALIDATION_FAILED')
            config = found[0].get('options',{}).get('indexConfig',{})
            if (found[0].get('state') != 'ONLINE' or type(config.get('vector.dimensions')) is not int
                    or config['vector.dimensions'] != 3072
                    or str(config.get('vector.similarity_function','')).lower() != 'cosine'):
                _invalid('SOURCE_VALIDATION_FAILED')


def _readback(reader, records, contract):
    selected = {(r.entity_type,r.entity_id):r for r in records}
    keys = sorted(selected)
    try:
        nodes = reader.read_nodes([list(k) for k in keys]) if keys else []
    except Exception:
        raise ArtifactFailure(VerificationState.UNAVAILABLE) from None
    seen = set()
    for node in nodes:
        kinds = [k for k in TARGETS if contract['namespace']+'.'+k in node['labels']]
        if len(kinds) != 1:
            _invalid('SOURCE_VALIDATION_FAILED')
        kind = kinds[0]
        props = node['properties']
        if (set(node['labels']) - {contract['namespace']+'.'+kind,'Entity'}
                or set(props) - {r['schema_name'] for r in contract['node_properties'][kind]}
                - {field for _,field in TARGETS[kind]}):
            _invalid('SOURCE_VALIDATION_FAILED')
        decoded = decode_properties(props,contract['node_properties'][kind])
        key = contract['namespace']+'.'+kind,decoded['id']
        if key in seen or key not in selected or _freeze(decoded) != selected[key].metadata:
            _invalid('SOURCE_VALIDATION_FAILED')
        seen.add(key)
        for record in records:
            if (record.entity_type,record.entity_id) == key and props.get(record.physical_field) != record.source_text:
                _invalid('SOURCE_VALIDATION_FAILED')
    if seen != set(keys):
        _invalid('SOURCE_VALIDATION_FAILED')
    relations = {}
    for record in records:
        for relation in record.graph_context:
            key = (*relation['from'],relation['predicate'],*relation['to'])
            if key in relations and relations[key] != relation:
                _invalid('SOURCE_VALIDATION_FAILED')
            relations[key] = relation
    try:
        edges = reader.read_edges([list(k) for k in sorted(relations)]) if relations else []
    except Exception:
        raise ArtifactFailure(VerificationState.UNAVAILABLE) from None
    seen = set()
    for edge in edges:
        endpoints = []
        for side in ('from','to'):
            labels = [l for l in edge[side]['labels'] if l in
                {contract['namespace']+'.'+k for k in TARGETS}]
            props = edge[side]['properties']
            if (len(labels) != 1 or set(edge[side]['labels']) - {labels[0],'Entity'}
                    or props.get('name') != props.get('id')
                    or any(props.get(flag) not in (None,False,'false') for flag in
                           ('stub','degraded','_stub','_degraded','isStub','isDegraded'))):
                _invalid('SOURCE_VALIDATION_FAILED')
            endpoints.extend((labels[0],props['id']))
        key = (*endpoints[:2],edge['predicate'],*endpoints[2:])
        if key not in relations or key in seen:
            _invalid('SOURCE_VALIDATION_FAILED')
        rows = contract['relation_properties'][edge['predicate']]
        if set(edge['properties']) - {r['schema_name'] for r in rows}:
            _invalid('SOURCE_VALIDATION_FAILED')
        properties = decode_properties(edge['properties'],rows)
        if _freeze(properties) != relations[key]['properties']:
            _invalid('SOURCE_VALIDATION_FAILED')
        seen.add(key)
    if seen != set(relations):
        _invalid('SOURCE_VALIDATION_FAILED')


def verify_native_sources(result: AnswerResult, release: ServingRelease, reader,
                          as_of: date, webapp_snapshot_id: str | None) -> VerifiedSources:
    """Verify all actual citation types; never repair or classify native roles."""
    from kag.legal_solver import AnswerResult, Citation, _META, _current

    if (type(result) is not AnswerResult or type(result.abstained) is not bool
            or not _text(result.answer) or not result.answer.strip()
            or type(result.citations) is not tuple or any(type(c) is not Citation for c in result.citations)
            or result.abstained == bool(result.citations)):
        _invalid('INVALID_NATIVE_RESULT')
    try:
        if type(release) is not ServingRelease or type(as_of) is not date:
            _invalid()
        if reader is None:
            raise ArtifactFailure(VerificationState.UNAVAILABLE)
        _unchanged(release)
        publication = release.publication
        if publication is not None:
            if publication['snapshot_id'] != webapp_snapshot_id or publication['as_of'] != as_of.isoformat():
                _invalid()
        elif webapp_snapshot_id is not None:
            _invalid()
        _backend(reader,release)
        contract = _json(release.contract_bytes)
        lookup = {r.evidence_id:r for r in release.records}
        documents = {r.entity_id:r for r in release.records if r.entity_type.endswith('.LegalDocument')}
        resolved = []
        for citation in result.citations:
            record = lookup.get(citation.evidence_id)
            if (record is None or citation.doc_id != record.doc_id or citation.unit_id != record.unit_id
                    or citation.sign_id != record.sign_id or citation.field != record.field
                    or type(citation.start) is not int or type(citation.end) is not int
                    or citation.start != 0 or citation.end != len(record.source_text)
                    or not _text(citation.quote) or citation.quote != record.source_text):
                _invalid('SOURCE_VALIDATION_FAILED')
            kind = record.entity_type.rsplit('.',1)[1]
            allowed = {p for p,_ in TARGETS[kind]} | (_META[kind] if kind == 'LegalDocument' else set())
            if record.field not in allowed:
                _invalid('SOURCE_VALIDATION_FAILED')
            item = {'doc_id':record.doc_id,'sign_id':record.sign_id,'metadata':record.metadata}
            if not _current(item,{key:r.metadata for key,r in documents.items()},as_of):
                _invalid('SOURCE_VALIDATION_FAILED')
            resolved.append(record)
        read_records = list(resolved)
        for record in resolved:
            read_records.append(documents[record.doc_id])
        _readback(reader,read_records,contract)
        verified = []
        for citation, record in zip(result.citations,resolved):
            eligible = False
            if publication is not None and record.entity_type.endswith('.LegalUnit') and record.field == 'text':
                doc = next((d for d in publication['documents'] if d['doc_id'] == record.doc_id),None)
                unit = next((u for u in publication['units'] if u['unit_id'] == record.entity_id),None)
                eligible = bool(doc and unit and doc['published'] and doc['current_effective']
                    and doc['replaces_eligible'] and unit['published'])
            verified.append(VerifiedSource(citation,record.entity_type,record.entity_id,record.source_text,
                                           eligible,record.source_sha256,record.physical_field))
        _backend(reader,release)
        _unchanged(release)
        return VerifiedSources(tuple(verified),release.release_id,release.descriptor['source_snapshot_id'],
            release.schema_contract,release.descriptor_sha256,as_of,webapp_snapshot_id,
            VerificationState.VERIFIED if publication is not None else VerificationState.UNVERIFIED)
    except ArtifactFailure:
        raise
    except OSError:
        raise ArtifactFailure(VerificationState.UNAVAILABLE) from None
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError):
        raise ArtifactFailure(VerificationState.INVALID,'SOURCE_VALIDATION_FAILED') from None


def release_view(release: ServingRelease) -> dict:
    """Artifact integrity view only. Step4/5 own all actual runtime gates."""
    return {'contract_version':'h1-read-v1.0','release_id':release.release_id,
        'release_kind':release.release_kind,'schema_contract':dict(release.schema_contract.__dict__),
        'source_snapshot_id':release.descriptor['source_snapshot_id'],
        'source_catalog_sha256':release.descriptor['source_catalog_sha256'],
        'release_descriptor_sha256':release.descriptor_sha256,
        'graph_fingerprint':release.descriptor['graph_fingerprint'],
        'backend_identity_verified':False,'source_identity_verified':False,'verified_at':None,
        'query_ready':False,'production_write':'blocked'}
