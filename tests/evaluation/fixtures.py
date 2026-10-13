"""Synthetic data only; product code never imports this module."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def record(**changes):
    result = dict(schema_version='1.0', dataset_version='synthetic',
                  dataset_status='PROVISIONAL', qid='q1', question='Câu hỏi synthetic?',
                  category='definition', expected_abstain=False)
    result.update(changes)
    return result


def load_fixture(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def module(name):
    import importlib
    try:
        return importlib.import_module('kag.evaluation.' + name)
    except ModuleNotFoundError as exc:
        raise AssertionError('evaluation feature missing: ' + name) from exc
