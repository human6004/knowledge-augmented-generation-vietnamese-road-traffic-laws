"""Read-only process/dataset inspection. No graph client, execution or provider access."""
from itertools import islice
from pathlib import Path
import re

from kag.evaluation.dataset import load_dataset
from kag.evaluation.models import ValidationError

LIMIT_BYTES = 8 * 1024 * 1024


def pipeline_view(supervisor):
    busy = supervisor.busy if supervisor is not None else None
    closed = supervisor.closed if supervisor is not None else None
    draining = supervisor.draining if supervisor is not None else None
    phase = ('unavailable' if supervisor is None else 'closed' if closed
             else 'draining' if draining else 'running' if busy else 'idle')
    return {'contract_version': 'h1-inspect-v1.0', 'phase': phase,
            'active_requests': int(busy) if busy is not None else None,
            'draining': draining, 'closed': closed,
            # The upstream pipeline has no verified stage/percentage reporter.
            'progress': None, 'execution_allowed': False,
            'operational_proof': 'DENY', 'production_write': 'BLOCKED', 'provider_egress': 'DENY'}


def _files(root):
    candidates = []
    entries = list(islice(root.iterdir(), 513))
    if len(entries) > 512:
        raise OverflowError
    for entry in sorted(entries):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', entry.name) or entry.is_symlink():
            continue
        if entry.is_file() and entry.suffix == '.jsonl':
            candidates.append(entry)
        elif entry.is_dir():
            path = entry/'eval_questions.jsonl'
            if path.is_file() and not path.is_symlink():
                candidates.append(path)
        if len(candidates) > 20:
            raise OverflowError
    return candidates


def _dataset(path, root):
    row = {'id': path.relative_to(root).as_posix(), 'dataset_status': None,
           'dataset_eligibility': 'BLOCKED', 'reason': 'INVALID_DATASET',
           'dataset_hash': None, 'record_count': None, 'official_benchmark': False}
    try:
        if path.stat().st_size > LIMIT_BYTES:
            row['reason'] = 'DATASET_TOO_LARGE'
            return row
        manifest = path.with_name('eval_questions.manifest.json')
        if manifest.exists() and (manifest.is_symlink() or not manifest.is_file()
                                  or manifest.stat().st_size > LIMIT_BYTES):
            return row
        dataset = load_dataset(path)
        status = dataset.records[0].dataset_status
        # Only the existing framework can establish canonical FROZEN integrity.
        official = dataset.official_benchmark
        gold = any(record.gold_doc_ids or record.gold_unit_ids or record.gold_sign_ids
                   or record.expected_abstain for record in dataset.records)
        eligible = status == 'FROZEN' and gold
        row.update(dataset_status=status, dataset_hash=dataset.dataset_hash,
                   record_count=len(dataset.records), official_benchmark=official,
                   dataset_eligibility='ELIGIBLE' if eligible else 'BLOCKED',
                   reason=None if eligible else 'PROVISIONAL_DATASET' if status == 'PROVISIONAL' else 'NO_GOLD')
    except (OSError, ValueError, ValidationError, KeyError, RecursionError):
        pass
    return row


def dataset_catalog(root=None):
    result = {'contract_version': 'h1-inspect-v1.0', 'state': 'NOT_CONFIGURED',
              'datasets': [], 'execution_allowed': False,
              'execution_blockers': ['OPERATIONAL_PROOF_REQUIRED', 'BENCHMARK_EXECUTION_NOT_AUTHORIZED'],
              'metrics': None}
    if root is None:
        return result
    try:
        root = Path(root)
        if not root.is_absolute() or root.is_symlink() or not root.is_dir():
            raise OSError
        files = _files(root)
        result.update(state='AVAILABLE', datasets=[_dataset(path, root) for path in files])
    except OverflowError:
        result['state'] = 'LIMIT_EXCEEDED'
    except (OSError, ValueError):
        result['state'] = 'UNAVAILABLE'
    return result
