"""Offline source loading and fail-closed integrity checks.

Frozen containers and their dictionaries are immutable by convention. Locators
are repository-relative for corpus files and artifact names for external ledger.
No full-source runner or count-based production-plan verification lives here.
"""
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from .codec import BuilderContractError, canonical_json, validate_properties


ARTIFACT_HASHES = (
    ('xref_a3g2_final_ledger.jsonl', '1dea69f2c2b3ac344478ef24b1844f06514c4150a069e1c6d5cc5f9ffe8fecb4'),
    ('xref_a3g2_final_audit.json', '2a130da7f4c6ad0bb673366e9bb6e390f3e481cb5381003933f3195eb23e1fb3'),
    ('xref_a3g2_downstream_policy.json', 'dcd12c131a9033efaf8f93703cf5423d59e3827f242249a5727759cb49d42b0e'),
)
SOURCE_FILES = (
    ('documents', 'data/processed/meta/documents.jsonl'),
    ('units', 'data/processed/units/units.jsonl'),
    ('penalties', 'data/processed/penalties/penalties.jsonl'),
    ('signs', 'data/processed/signs/signs.jsonl'),
    ('relations', 'data/processed/meta/relations.jsonl'),
    ('xrefs', 'data/processed/meta/xrefs.jsonl'),
)
CLASSIFICATIONS = ('SAFE_EDGE', 'EXTERNAL_REFERENCE_ONLY',
                   'KEEP_UNRESOLVED_NO_EDGE', 'EXCLUDE_FROM_GRAPH_EDGE')


class InputIntegrityError(BuilderContractError):
    """Invalid source identity, hierarchy, join or artifact integrity."""


@dataclass(frozen=True)
class SourceRecord:
    record: dict[str, Any]
    locator: dict[str, Any]


@dataclass(frozen=True)
class BuilderInputs:
    documents: tuple[SourceRecord, ...]
    units: tuple[SourceRecord, ...]
    penalties: tuple[SourceRecord, ...]
    signs: tuple[SourceRecord, ...]
    relations: tuple[SourceRecord, ...]
    xrefs: tuple[SourceRecord, ...]
    ledger: tuple[SourceRecord, ...]
    markdown_paths: frozenset[str]
    artifact_hashes: dict[str, str]


@dataclass(frozen=True)
class ValidatedInputs:
    raw: BuilderInputs
    documents: dict[str, SourceRecord]
    units: dict[str, SourceRecord]
    signs: dict[str, SourceRecord]
    penalties: dict[str, SourceRecord]
    xref_ledger: dict[str, SourceRecord]


def _error(row: SourceRecord, reason: str) -> InputIntegrityError:
    return InputIntegrityError(f"{row.locator['source_path']}:{row.locator['line']}: {reason}")


def xref_fingerprint(source_record: Mapping[str, Any]) -> str:
    """Hash ALL untouched original fields, before gates or property preparation."""
    return hashlib.sha256(canonical_json(source_record).encode('utf-8')).hexdigest()


def _index(rows: tuple[SourceRecord, ...], field: str) -> dict[str, SourceRecord]:
    result = {}
    for row in rows:
        value = row.record.get(field)
        if not isinstance(value, str) or not value.strip():
            raise _error(row, f'{field}: missing/non-text/blank identity')
        if value in result:
            raise _error(row, f'duplicate {field} {value!r}')
        result[value] = row
    return result


def _node_values(
    node_type: str, row: SourceRecord, penalty: SourceRecord | None = None,
) -> dict[str, Any]:
    """Prepare logical properties once for validation and mapping; never mutate source."""
    record = row.record
    id_field = {'LegalDocument': 'doc_id', 'LegalUnit': 'unit_id', 'TrafficSign': 'sign_id'}[node_type]
    values = dict(record, id=record[id_field], name=record[id_field], source_record=dict(row.locator))
    if node_type == 'LegalDocument':
        values['markdown_path'] = f"data/processed/documents/{record['doc_id']}.md"
        for primary, alias in (('effective_from', 'ngay_hieu_luc'), ('effective_to', 'ngay_het_hieu_luc')):
            if record.get(primary) is not None and record.get(alias) is not None and record[primary] != record[alias]:
                raise _error(row, f'{primary}: date alias conflict with {alias}')
            values[primary] = record[primary] if primary in record else record.get(alias)
    elif node_type == 'LegalUnit':
        # Penalty properties are derived exclusively from the joined penalty row.
        values = {key: value for key, value in values.items() if not key.startswith('penalty_')}
        if penalty is not None:
            for key in ('penalty_id', 'dieu_title', 'doi_tuong', 'hanh_vi', 'phat_tien_min',
                        'phat_tien_max', 'canh_cao', 'tru_diem_gplx', 'tich_thu'):
                logical = key if key == 'penalty_id' else 'penalty_' + key
                values[logical] = penalty.record.get(key)
            span = penalty.record.get('tuoc_gplx_thang')
            if span is not None:
                if not isinstance(span, list) or len(span) != 2 or any(type(x) is not int for x in span):
                    raise _error(penalty, 'penalty tuoc_gplx_thang: expected two native ints')
                values['penalty_tuoc_gplx_thang_min'], values['penalty_tuoc_gplx_thang_max'] = span
            values['penalty_source_record'] = {'record': penalty.record, 'locator': penalty.locator}
    return values


def _validate_node(node_type: str, row: SourceRecord, contract: Mapping[str, Any],
                   penalty: SourceRecord | None = None) -> None:
    try:
        validate_properties(_node_values(node_type, row, penalty),
                            contract['node_properties'][node_type], contract['unit_type_values'])
    except BuilderContractError as exc:
        raise _error(row, str(exc)) from exc


def validate_input_integrity(inputs: BuilderInputs, contract: Mapping[str, Any]) -> ValidatedInputs:
    """Validate the complete source/ledger join before inspecting SAFE_EDGE rows."""
    documents = _index(inputs.documents, 'doc_id')
    documents = {key: row for key, row in documents.items()
                 if row.record.get('scope') != 'out_of_scope'
                 and f'data/processed/documents/{key}.md' in inputs.markdown_paths}
    units = _index(inputs.units, 'unit_id')
    signs = _index(inputs.signs, 'sign_id')
    for row in documents.values():
        _validate_node('LegalDocument', row, contract)
    for identity, row in units.items():
        record = row.record
        if record.get('doc_id') not in documents:
            raise _error(row, f'unit {identity!r}: missing production doc {record.get("doc_id")!r}')
        if 'parent_id' not in record:
            raise _error(row, f'unit {identity!r}: parent_id key missing')
        parent = record['parent_id']
        if parent is not None:
            if not isinstance(parent, str) or parent not in units:
                raise _error(row, f'unit {identity!r}: parent {parent!r} missing')
            if units[parent].record['doc_id'] != record['doc_id']:
                raise _error(row, f'unit {identity!r}: cross-document parent {parent!r}')
        _validate_node('LegalUnit', row, contract)
    # Iterative parent walk: linear in the number of units, safe for deep trees.
    complete = set()
    for identity in units:
        path = set()
        current = identity
        while current is not None and current not in complete:
            if current in path:
                raise _error(units[current], f'hierarchy cycle at unit_id {current!r}')
            path.add(current)
            current = units[current].record['parent_id']
        complete.update(path)
    penalties = {}
    for row in inputs.penalties:
        record = row.record
        target = record.get('unit_id')
        if not isinstance(target, str) or target not in units:
            raise _error(row, f'orphan penalty unit_id {target!r}')
        if target in penalties:
            raise _error(row, f'duplicate penalty target {target!r}')
        if record.get('penalty_id') != target:
            raise _error(row, f'penalty_id {record.get("penalty_id")!r} != unit_id {target!r}')
        if record.get('doc_id') != units[target].record['doc_id']:
            raise _error(row, f'penalty {target!r}: document mismatch')
        _validate_node('LegalUnit', row=units[target], contract=contract)
        try:
            values = _node_values('LegalUnit', units[target], row)
            validate_properties(values, contract['node_properties']['LegalUnit'], contract['unit_type_values'])
        except BuilderContractError as exc:
            raise _error(row, f'penalty {target!r}: {exc}') from exc
        for low, high in (('penalty_phat_tien_min', 'penalty_phat_tien_max'),
                          ('penalty_tuoc_gplx_thang_min', 'penalty_tuoc_gplx_thang_max')):
            minimum, maximum = values.get(low), values.get(high)
            if ((minimum is not None and minimum < 0) or (maximum is not None and maximum < 0)
                    or (minimum is not None and maximum is not None and minimum > maximum)):
                raise _error(row, f'penalty {target!r}: invalid range {low}/{high}')
        penalties[target] = row
    for identity, row in signs.items():
        target = row.record.get('unit_id')
        if not isinstance(target, str) or target not in units:
            raise _error(row, f'orphan sign {identity!r}: unit_id {target!r}')
        if row.record.get('doc_id') != units[target].record['doc_id']:
            raise _error(row, f'sign {identity!r}: document mismatch')
        _validate_node('TrafficSign', row, contract)
    source_by_hash = {}
    for row in inputs.xrefs:
        fingerprint = xref_fingerprint(row.record)
        if fingerprint in source_by_hash:
            raise _error(row, f'duplicate source fingerprint {fingerprint}')
        source_by_hash[fingerprint] = row
    ledger = _index(inputs.ledger, 'record_fingerprint')
    missing = source_by_hash.keys() - ledger.keys()
    extra = ledger.keys() - source_by_hash.keys()
    if missing:
        fingerprint = min(missing)
        raise _error(source_by_hash[fingerprint], f'ledger missing fingerprint {fingerprint}')
    if extra:
        fingerprint = min(extra)
        raise _error(ledger[fingerprint], f'ledger extra fingerprint {fingerprint}')
    classification_field = contract['xref_contract']['classification_field']
    for fingerprint, source in source_by_hash.items():
        approved = ledger[fingerprint]
        record = source.record
        for key in sorted(record.keys() & approved.record.keys()):
            if canonical_json(record[key]) != canonical_json(approved.record[key]):
                raise _error(source, f'source/ledger invariant conflict {key}: {fingerprint}')
        classification = approved.record.get(classification_field)
        if classification not in CLASSIFICATIONS:
            raise _error(approved, f'invalid classification {classification!r}')
        if classification != contract['xref_contract']['allowed_classification']:
            continue
        if type(record.get('is_exclusion')) is not bool or record.get('in_corpus') is not True:
            raise _error(source, 'SAFE_EDGE requires exact bool polarity and in_corpus=True')
        evidence = record.get('evidence')
        if not isinstance(evidence, str) or not evidence.strip():
            raise _error(source, 'SAFE_EDGE evidence missing/blank')
        for side in ('from', 'to'):
            identity, document = record.get(side+'_unit_id'), record.get(side+'_doc_id')
            if not isinstance(identity, str) or identity not in units or document not in documents:
                raise _error(source, f'SAFE_EDGE {side} endpoint missing/non-production {identity!r}')
            if units[identity].record['doc_id'] != document:
                raise _error(source, f'SAFE_EDGE {side} document mismatch {identity!r}')
    return ValidatedInputs(inputs, documents, units, signs, penalties, ledger)


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise InputIntegrityError(f'{path.name}: cannot read input: {exc}') from exc


def _jsonl(data: bytes, relative_path: str) -> tuple[SourceRecord, ...]:
    digest = hashlib.sha256(data).hexdigest()
    result = []
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise InputIntegrityError(f'{relative_path}: invalid UTF-8: {exc}') from exc
    # JSONL uses LF; Unicode LS/PS/NEL inside JSON strings are source Text.
    for line, raw in enumerate(text.split('\n'), 1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise InputIntegrityError(f'{relative_path}:{line}: invalid JSON: {exc.msg}') from exc
        if not isinstance(record, dict):
            raise InputIntegrityError(f'{relative_path}:{line}: expected JSON object')
        result.append(SourceRecord(record, dict(source_path=relative_path, file_sha256=digest, line=line)))
    return tuple(result)


def load_inputs(
    project_root: str | Path, ledger_path: str | Path, audit_path: str | Path,
    policy_path: str | Path, contract: Mapping[str, Any],
    *, expected_artifact_hashes: Mapping[str, str] | None = None,
) -> ValidatedInputs:
    """Load only whitelisted source families; verify all artifacts before parsing.

    Defaults pin the approved production artifacts. Synthetic disk fixtures must
    explicitly supply expected_artifact_hashes and their own xref contract SHA.
    Counts and full-source plan verification are deferred to C3.
    """
    root = Path(project_root)
    expected = dict(ARTIFACT_HASHES) if expected_artifact_hashes is None else expected_artifact_hashes
    artifacts = {}
    hashes = {}
    for (name, _), path in zip(ARTIFACT_HASHES, (ledger_path, audit_path, policy_path)):
        path = Path(path)
        if path.name != name:
            raise InputIntegrityError(f'{path.name}: expected artifact name {name}')
        data = _read(path)
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected.get(name):
            raise InputIntegrityError(f'{name}: SHA256 mismatch')
        artifacts[name], hashes[name] = data, digest
    for name, _ in ARTIFACT_HASHES[1:]:
        try:
            metadata = json.loads(artifacts[name])
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise InputIntegrityError(f'{name}: invalid JSON') from exc
        if not isinstance(metadata, dict):
            raise InputIntegrityError(f'{name}: expected JSON object')
    source_data = {family: _read(root / relative) for family, relative in SOURCE_FILES}
    if hashlib.sha256(source_data['xrefs']).hexdigest() != contract['xref_contract']['xref_sha256']:
        raise InputIntegrityError('data/processed/meta/xrefs.jsonl: SHA256 mismatch')
    rows = {family: _jsonl(source_data[family], relative) for family, relative in SOURCE_FILES}
    markdown = frozenset(path.relative_to(root).as_posix()
                         for path in (root/'data/processed/documents').glob('*.md') if path.is_file())
    inputs = BuilderInputs(**rows, ledger=_jsonl(artifacts[ARTIFACT_HASHES[0][0]], ARTIFACT_HASHES[0][0]),
                           markdown_paths=markdown, artifact_hashes=hashes)
    return validate_input_integrity(inputs, contract)
