"""Durability and locking contracts; all outputs live outside the checkout."""
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
IDENTITY = {'run_id': 'sample-001', 'scope': 'C4_3A_MANIFEST_SAMPLE',
            'database_id': 'physical-db-1', 'batch_size': 2, 'plan_hash': 'a' * 64}


class RunStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / IDENTITY['run_id']

    def api(self):
        self.assertTrue((ROOT / 'kag/run_state.py').is_file(), 'run state implementation missing')
        return importlib.import_module('kag.run_state')

    def state(self, **kwargs):
        state = self.api().RunState(self.directory, IDENTITY, **kwargs)
        self.addCleanup(state.close)
        return state

    def records(self, name):
        return [json.loads(line) for line in (self.directory / name).read_text().splitlines()]

    def test_atomic_status_has_exact_contract_and_monotonic_progress(self):
        state = self.state()
        state.update('plan', 'RUNNING', 1, 2)
        status = json.loads((self.directory / 'status.json').read_text())
        self.assertEqual(set(status), {'run_id', 'scope', 'stage', 'state', 'done', 'total',
            'started_at', 'updated_at', 'heartbeat', 'error_code', 'sanitized_error'})
        self.assertEqual((status['stage'], status['done'], status['total']), ('plan', 1, 2))
        self.assertTrue(status['heartbeat'].endswith('Z'))
        with self.assertRaises(self.api().RunBlocked):
            state.update('plan', 'RUNNING', 0, 2)
        state.update('vectorize', 'RUNNING', 0, 3)

    def test_failed_replace_keeps_previous_snapshot_and_removes_own_temp(self):
        api = self.api()
        path = Path(self.temp.name) / 'snapshot.json'
        api.atomic_json(path, {'old': 1})
        with patch('kag.run_state.os.replace', side_effect=OSError('secret-do-not-log')):
            with self.assertRaises(OSError):
                api.atomic_json(path, {'new': 2})
        self.assertEqual(json.loads(path.read_text()), {'old': 1})
        self.assertEqual(list(path.parent.iterdir()), [path])

    def test_resume_preserves_confirmations_without_duplicate_audit_records(self):
        state = self.state()
        state.begin_batch('vectorize', 'batch-1', 'b' * 64)
        state.confirm_batch('vectorize', 'batch-1', {'successful': 2, 'output_hash': 'c' * 64})
        state.finish_stage('vectorize', {'successful': 2})
        before = (self.directory / 'batches.jsonl').read_bytes()
        state.close()
        resumed = self.state(resume=True)
        self.assertEqual(resumed.identity, IDENTITY)
        self.assertEqual(resumed.begin_batch('vectorize', 'batch-1', 'b' * 64)['state'], 'CONFIRMED')
        resumed.confirm_batch('vectorize', 'batch-1', {'successful': 2, 'output_hash': 'c' * 64})
        self.assertEqual((self.directory / 'batches.jsonl').read_bytes(), before)
        self.assertEqual(resumed.completed_stage('vectorize'), {'successful': 2})

    def test_changed_identity_or_batch_source_is_blocked(self):
        api = self.api()
        state = self.state()
        state.begin_batch('plan', 'one', 'a' * 64)
        with self.assertRaises(api.RunBlocked):
            state.begin_batch('plan', 'one', 'b' * 64)
        state.close()
        with self.assertRaises(api.RunBlocked):
            api.RunState(self.directory, dict(IDENTITY, batch_size=3), resume=True)

    def test_confirmation_requires_intent_and_is_immutable(self):
        state = self.state()
        with self.assertRaises(self.api().RunBlocked):
            state.confirm_batch('plan', 'unknown', {'n': 1})
        state.begin_batch('plan', 'one', 'a' * 64)
        state.confirm_batch('plan', 'one', {'n': 1})
        with self.assertRaises(self.api().RunBlocked):
            state.confirm_batch('plan', 'one', {'n': 2})

    def test_invalid_stage_never_becomes_durable_pass(self):
        state = self.state()
        with self.assertRaises(self.api().RunBlocked):
            state.finish_stage('skip-everything', {'pass': True})
        self.assertIsNone(state.completed_stage('skip-everything'))

    def test_stage_pass_and_audit_status_commit_together(self):
        state = self.state()
        with patch.object(state, 'update', side_effect=RuntimeError('crash-before-PASS')):
            with self.assertRaises(RuntimeError):
                state.finish_stage('plan', {'count': 2})
        state.close()
        resumed = self.state(resume=True)
        self.assertIsNone(resumed.completed_stage('plan'))
        self.assertNotEqual(resumed.status['state'], 'PASS')

    def test_heartbeat_publication_failure_prevents_pass_and_new_batch(self):
        state = self.state()
        api = self.api()
        publish = api.atomic_json
        failed = threading.Event()
        def broken(path, value):
            if threading.current_thread().name == 'kag-heartbeat':
                failed.set()
                raise OSError('NEVER_LOG_HEARTBEAT_SECRET')
            return publish(path, value)
        with patch('kag.run_state.atomic_json', broken), patch('threading.excepthook'):
            state.start_heartbeat(0.005)
            self.assertTrue(failed.wait(1))
            state._heartbeat_thread.join(timeout=1)
        with self.assertRaises(RuntimeError): state.finish_stage('plan', {'count': 2})
        with self.assertRaises(RuntimeError): state.begin_batch('plan', 'one', 'a' * 64)
        self.assertIsNone(state.completed_stage('plan'))
        state.update('plan', 'ERROR', 0, 1, error_code='RUNTIME')
        self.assertNotIn('NEVER_LOG_HEARTBEAT_SECRET', (self.directory / 'status.json').read_text())

    def test_resume_refuses_ledger_symlink_before_mutating_target(self):
        api = self.api()
        original = self.state()
        original.close()
        original_bytes = (self.directory / 'ledger.sqlite3').read_bytes()
        other = Path(self.temp.name) / 'alias-run'
        other.mkdir()
        (other / 'ledger.sqlite3').symlink_to(self.directory / 'ledger.sqlite3')
        with self.assertRaises(api.RunBlocked):
            api.RunState(other, IDENTITY, resume=True)
        self.assertEqual((self.directory / 'ledger.sqlite3').read_bytes(), original_bytes)

    def test_pending_outbox_recovers_after_crash_before_append(self):
        state = self.state()
        state.begin_batch('plan', 'one', 'a' * 64)
        with patch.object(state, '_flush_outbox', side_effect=OSError('crash')):
            with self.assertRaises(OSError):
                state.confirm_batch('plan', 'one', {'n': 1})
        state.close()
        resumed = self.state(resume=True)
        self.assertEqual(resumed.begin_batch('plan', 'one', 'a' * 64)['state'], 'CONFIRMED')
        confirmed = [r for r in self.records('batches.jsonl') if r['state'] == 'CONFIRMED']
        self.assertEqual(len(confirmed), 1)

    def test_outbox_recovers_append_before_sqlite_ack_without_duplicate(self):
        state = self.state()
        state.begin_batch('plan', 'one', 'a' * 64)
        with patch.object(state, '_ack_outbox', side_effect=OSError('crash-after-append')):
            with self.assertRaises(OSError):
                state.confirm_batch('plan', 'one', {'n': 1})
        state.close()
        self.state(resume=True)
        confirmed = [r for r in self.records('batches.jsonl') if r['state'] == 'CONFIRMED']
        self.assertEqual(len(confirmed), 1)

    def test_audit_hash_chains_bind_every_record(self):
        state = self.state()
        state.begin_batch('plan', 'one', 'a' * 64)
        state.confirm_batch('plan', 'one', {'n': 1})
        for name in ('events.jsonl', 'batches.jsonl'):
            previous = '0' * 64
            for sequence, record in enumerate(self.records(name), 1):
                self.assertEqual(record['sequence'], sequence)
                self.assertEqual(record['previous_hash'], previous)
                claimed = record.pop('record_hash')
                payload = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
                self.assertEqual(claimed, hashlib.sha256(payload.encode()).hexdigest())
                previous = claimed

    def test_torn_tampered_and_deleted_acknowledged_audit_tail_block_resume(self):
        api = self.api()
        for change in ('torn', 'tampered', 'deleted'):
            with self.subTest(change=change):
                directory = Path(self.temp.name) / change
                state = api.RunState(directory, IDENTITY)
                state.begin_batch('plan', 'one', 'a' * 64)
                state.close()
                path = directory / 'batches.jsonl'
                raw = path.read_bytes()
                altered = {'torn': raw + b'{', 'tampered': raw.replace(b'INTENT', b'BROKEN'), 'deleted': b''}[change]
                path.write_bytes(altered)
                with self.assertRaises(api.RunBlocked):
                    api.RunState(directory, IDENTITY, resume=True)
                self.assertEqual(path.read_bytes(), altered)

    def test_status_reconstructs_from_ledger_and_receipt_is_atomic(self):
        state = self.state()
        state.update('verify', 'RUNNING', 1, 2)
        state.finish_stage('verify', {'fingerprint': 'f' * 64})
        state.close()
        (self.directory / 'status.json').unlink()
        self.state(resume=True)
        status = json.loads((self.directory / 'status.json').read_text())
        receipt = json.loads((self.directory / 'receipt.json').read_text())
        self.assertEqual(status['stage'], 'verify')
        self.assertEqual(receipt['stages']['verify']['fingerprint'], 'f' * 64)

    def test_heartbeat_advances_without_using_sqlite_in_background(self):
        state = self.state()
        state.start_heartbeat(0.02)
        first = json.loads((self.directory / 'status.json').read_text())['heartbeat']
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            latest = json.loads((self.directory / 'status.json').read_text())['heartbeat']
            if latest != first:
                break
            time.sleep(0.01)
        self.assertNotEqual(latest, first)
        state.close()
        self.assertFalse(state._heartbeat_thread.is_alive())

    def test_unknown_error_content_is_never_persisted(self):
        state = self.state()
        state.update('vectorize', 'ERROR', 0, 1, error_code='api-key-secret-source-text')
        contents = ''.join(path.read_text() for path in self.directory.glob('*.json*'))
        self.assertNotIn('api-key-secret-source-text', contents)
        self.assertEqual(json.loads((self.directory / 'status.json').read_text())['error_code'], 'RUNTIME')

    def test_lock_contention_stale_owner_and_wrong_token_fail_closed(self):
        api = self.api()
        root = Path(self.temp.name) / 'locks'
        owner = api.GraphLock(root, 'physical-db-1', {'run_id': 'first', 'pid': 123})
        owner.acquire()
        other = api.GraphLock(root, 'physical-db-1', {'run_id': 'second', 'pid': 999999999})
        with self.assertRaises(api.RunBlocked):
            other.acquire()
        with self.assertRaises(api.RunBlocked):
            other.release()
        self.assertTrue(owner.path.is_file())
        owner.release()
        other.acquire()
        other.release()

    def test_run_paths_reject_traversal_repo_overlap_and_symlink_alias(self):
        api = self.api()
        base = Path(self.temp.name)
        for run_id in ('../escape', '..', '/absolute', 'a/b', 'a\\b', 'CON', 'trailing.'):
            with self.subTest(run_id=run_id), self.assertRaises(api.RunBlocked):
                api.validate_run_directory(base, run_id, repo_root=ROOT, read_only_paths=[])
        with self.assertRaises(api.RunBlocked):
            api.validate_run_directory(ROOT, 'run', repo_root=ROOT, read_only_paths=[])
        artifact = base / 'old' / 'vector.jsonl'
        with self.assertRaises(api.RunBlocked):
            api.validate_run_directory(base, 'old', repo_root=ROOT, read_only_paths=[artifact])
        alias = base / 'alias'
        alias.symlink_to(ROOT, target_is_directory=True)
        with self.assertRaises(api.RunBlocked):
            api.validate_run_directory(alias, 'run', repo_root=ROOT, read_only_paths=[])


if __name__ == '__main__':
    unittest.main()
