"""Canonical UTF-8/LF snapshots and strict JSONL validation."""
from dataclasses import replace
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from kag.builder.codec import canonical_json
from .models import EvaluationRecord, ValidatedDataset, ValidationError, ValidationIssue, fail, obj, text, boolean, ids


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical_line(value):
    # Validate before reusing the existing codec (which permits nonfinite JSON).
    def check(v):
        if v is None or type(v) in (str,bool,int):
            return
        if type(v) is float and math.isfinite(v):
            return
        if type(v) is list:
            for item in v:
                check(item)
            return
        if type(v) is dict and all(type(k) is str for k in v):
            for item in v.values():
                check(item)
            return
        fail('', 'NON_JSON_VALUE')
    check(value)
    try:
        return canonical_json(value).encode('utf-8',errors='strict') + b'\n'
    except UnicodeError:
        fail('', 'INVALID_UNICODE')


def canonical_dataset_bytes(records):
    return b''.join(canonical_line(r.to_dict()) for r in sorted(records,key=lambda r:r.qid.encode('utf-8')))


def canonical_protocol_bytes(protocol):
    return canonical_line(protocol.to_dict())


def strict_json(raw):
    def pairs(items):
        result = {}
        for key,value in items:
            if key in result:
                fail(key,'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    def constant(value):
        fail('', 'NONFINITE_JSON')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)


def _records(payloads, *, path='', lines=None):
    records, issues, seen, meta = [], [], set(), None
    for index,payload in enumerate(payloads):
        line = lines[index] if lines else index + 1
        qid = payload.get('qid') if type(payload) is dict and type(payload.get('qid')) is str else None
        try:
            record = EvaluationRecord.from_dict(payload)
            if record.qid in seen:
                fail('qid','DUPLICATE_QID')
            seen.add(record.qid)
            key = (record.schema_version,record.dataset_version,record.dataset_status)
            if meta is not None and meta != key:
                fail('dataset_version','MIXED_DATASET')
            meta = key
            records.append(record)
        except ValidationError as exc:
            issues.extend(replace(i,path=path,line=line,qid=qid) for i in exc.issues)
    if not payloads:
        issues.append(ValidationIssue(path=path,line=1,code='EMPTY_DATASET'))
    if issues:
        raise ValidationError(issues)
    raw = canonical_dataset_bytes(records)
    return ValidatedDataset(tuple(records),None,sha256(raw),raw)


def dataset_from_records(payloads):
    return _records(list(payloads))


def _parse(raw, path=''):
    try:
        text = raw.decode('utf-8',errors='strict')
        if '\ufeff' == text[:1] or text.lstrip('\r\n').startswith('\ufeff'):
            fail('', 'BOM_NOT_ALLOWED')
    except UnicodeError:
        raise ValidationError((ValidationIssue(path=path,line=1,code='INVALID_UTF8'),)) from None
    except ValidationError as exc:
        raise ValidationError(tuple(replace(i,path=path,line=1) for i in exc.issues)) from None
    payloads, lines, issues = [], [], []
    for line,content in enumerate(text.split('\n'),1):
        if not content.strip():
            continue
        try:
            payloads.append(strict_json(content))
            lines.append(line)
        except ValidationError as exc:
            issues.extend(replace(i,path=path,line=line) for i in exc.issues)
        except (ValueError,TypeError):
            issues.append(ValidationIssue(path=path,line=line,code='INVALID_JSON'))
    try:
        ds = _records(payloads,path=path,lines=lines)
    except ValidationError as exc:
        issues.extend(exc.issues)
    if issues:
        raise ValidationError(issues)
    return replace(ds,source_sha256=sha256(raw))


def load_dataset(path, manifest_path=None):
    path = Path(path)
    raw = path.read_bytes()
    ds = _parse(raw,str(path))
    if ds.records[0].dataset_status == 'FROZEN':
        target = Path(manifest_path) if manifest_path else path.with_name('eval_questions.manifest.json')
        if not target.is_file():
            fail('manifest','FROZEN_MANIFEST_MISSING')
        try:
            manifest = strict_json(target.read_bytes().decode('utf-8'))
        except (UnicodeError,ValueError):
            fail('manifest','INVALID_MANIFEST')
        return verify_frozen(raw,manifest)
    if manifest_path is not None:
        fail('manifest','PROVISIONAL_MANIFEST_NOT_ALLOWED')
    return ds


def validate_dataset(path, manifest_path=None):
    try:
        load_dataset(path,manifest_path)
        return ()
    except ValidationError as exc:
        return exc.issues


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')


def validate_catalog(catalog):
    obj(catalog,('schema_version','identities'),('schema_version','identities'))
    if catalog['schema_version'] != '1.0':
        fail('schema_version','UNSUPPORTED_SCHEMA')
    obj(catalog['identities'],('document','unit','sign'),('document','unit','sign'))
    return {channel:ids(catalog['identities'][channel],channel) for channel in ('document','unit','sign')}


def verify_frozen(dataset_bytes, manifest):
    keys = ('schema_version','dataset_version','dataset_status','sha256','record_count',
            'category_counts','frozen_at','official_benchmark','source_sha256','source_dataset_version')
    obj(manifest,keys,keys)
    ds = _parse(dataset_bytes)
    first = ds.records[0]
    expected = dict(schema_version=first.schema_version,dataset_version=first.dataset_version,
                    dataset_status='FROZEN',sha256=ds.dataset_hash,record_count=len(ds.records),
                    category_counts=dict(Counter(r.category for r in ds.records)))
    if first.dataset_status != 'FROZEN' or dataset_bytes != ds.canonical_bytes:
        fail('dataset','NONCANONICAL_FROZEN')
    for name,value in expected.items():
        if manifest[name] != value or type(manifest[name]) is not type(value):
            fail(name,'MANIFEST_MISMATCH')
    if any(type(v) is not int or v <= 0 for v in manifest['category_counts'].values()):
        fail('category_counts','MANIFEST_MISMATCH')
    boolean(manifest['official_benchmark'],'official_benchmark')
    text(manifest['source_dataset_version'],'source_dataset_version',identity=True)
    if manifest['source_dataset_version'] == first.dataset_version:
        fail('dataset_version','NEW_VERSION_REQUIRED')
    if type(manifest['source_sha256']) is not str or len(manifest['source_sha256']) != 64 or any(c not in '0123456789abcdef' for c in manifest['source_sha256']):
        fail('source_sha256','INVALID_HASH')
    try:
        stamp = manifest['frozen_at']
        if type(stamp) is not str or not stamp.endswith('Z'):
            raise ValueError()
        parsed = datetime.fromisoformat(stamp[:-1]+'+00:00')
        if parsed.utcoffset().total_seconds() != 0 or 'T' not in stamp:
            raise ValueError()
    except (ValueError,TypeError,AttributeError):
        fail('frozen_at','INVALID_UTC_TIMESTAMP')
    return replace(ds,official_benchmark=manifest['official_benchmark'],manifest_verified=True)


def freeze_dataset(source, output_root, dataset_version, official_benchmark=False):
    source, output_root = Path(source), Path(output_root)
    text(dataset_version,'dataset_version',identity=True)
    boolean(official_benchmark,'official_benchmark')
    ds = load_dataset(source)
    if ds.records[0].dataset_status != 'PROVISIONAL':
        fail('dataset_status','PROVISIONAL_REQUIRED')
    if dataset_version == ds.records[0].dataset_version:
        fail('dataset_version','NEW_VERSION_REQUIRED')
    target = output_root / ('dataset-'+sha256(dataset_version.encode('utf-8')))
    if source.resolve() in (target.resolve(),(target/'eval_questions.jsonl').resolve()):
        fail('source','SOURCE_TARGET_COLLISION')
    frozen = dataset_from_records([dict(r.to_dict(),dataset_status='FROZEN',dataset_version=dataset_version) for r in ds.records])
    manifest = dict(schema_version='1.0',dataset_version=dataset_version,dataset_status='FROZEN',
                    sha256=frozen.dataset_hash,record_count=len(frozen.records),
                    category_counts=dict(Counter(r.category for r in frozen.records)),frozen_at=utc_now(),
                    official_benchmark=official_benchmark,source_sha256=ds.source_sha256,
                    source_dataset_version=ds.records[0].dataset_version)
    manifest_bytes = canonical_line(manifest)
    verify_frozen(frozen.canonical_bytes,manifest)
    output_root.mkdir(parents=True,exist_ok=True)
    target.mkdir(exist_ok=False)
    with (target/'eval_questions.jsonl').open('xb') as stream:
        stream.write(frozen.canonical_bytes)
    manifest_path = target/'eval_questions.manifest.json'
    with manifest_path.open('xb') as stream:
        stream.write(manifest_bytes)
    return manifest_path
