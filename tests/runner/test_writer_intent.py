"""TEST_WRITER_INTENT: pinned SDK serialization captured before HTTP dispatch."""
import asyncio
import copy
from dataclasses import replace
import unittest
from unittest.mock import patch

import test_runner as runner_fixture


class Captured(Exception): pass


class WriterIntentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): runner_fixture.RunnerPreflightTests.setUpClass()

    def setUp(self):
        self.case = runner_fixture.RunnerPreflightTests()
        self.case.adapter = runner_fixture.RunnerPreflightTests.adapter
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        config = self.case.production()
        config['write_mode'] = 'NO_OP'
        self.verified = self.case.preflight(config)
        self.config = self.verified['writer_config']
        self.adapter = self.case.adapter
        self.calls = []
        self.writer = self.adapter.NativeIntegerKGWriter(self.config)
        self.graph = self.adapter.to_subgraphs(self.case.nodes[:1], 1, 'nodes', self.config)[0]
        api_client = self.writer.client._rest_client.api_client
        def capture(method, url, **kwargs):
            self.calls.append((method, url, kwargs['body']))
            raise Captured()
        boundary = patch.object(api_client, 'request', side_effect=capture)
        boundary.start(); self.addCleanup(boundary.stop)
        for target in ('socket.create_connection', 'urllib3.connectionpool.HTTPConnectionPool.urlopen'):
            blocked = patch(target, side_effect=AssertionError('network dispatch forbidden'))
            blocked.start(); self.addCleanup(blocked.stop)
        self.addCleanup(self.config.backend_session.close)
        self.addCleanup(self.verified['source_index'].close)

    def test_pinned_chain_captures_native_project_and_exact_write_intent(self):
        with self.assertRaises(Captured): self.writer.write_subgraph(self.graph, 'nodes')
        self.assertEqual(len(self.calls), 1)
        method, url, body = self.calls[0]
        self.assertEqual((method, url), ('POST', self.config.host_addr+'/public/v1/graph/writerGraph'))
        self.assertIs(type(body['projectId']), int)
        self.assertEqual(body['projectId'], 37)
        self.assertEqual(body['operation'], 'UPSERT')
        self.assertIs(body['enableLeadTo'], False)

    def test_inherited_invoke_and_ainvoke_use_identity_guard(self):
        self.config.backend_session.close()
        with self.assertRaises(ValueError): self.writer.invoke(self.graph)
        async def invoke():
            return await self.writer.ainvoke(self.graph)
        with self.assertRaises(ValueError): asyncio.run(invoke())
        self.assertEqual(self.calls, [])

    def test_constructor_rejects_copied_missing_and_foreign_proof(self):
        for proof in (None, copy.copy(self.config.backend_proof),
                      replace(self.config.backend_proof, project_id=38)):
            with self.subTest(proof=proof is None), self.assertRaises(ValueError):
                replace(self.config, backend_proof=proof)
        self.assertEqual(self.calls, [])

    def test_stale_mutated_binding_and_swapped_client_block_before_dispatch(self):
        original = self.writer.client
        self.writer.client = self.adapter.GraphClient(host_addr=self.config.host_addr, project_id=37)
        with self.assertRaises(ValueError): self.writer.invoke(self.graph)
        self.writer.client = original
        object.__setattr__(self.config.backend_proof, 'physical_database_id', 'changed')
        with self.assertRaises(ValueError): self.writer.write_subgraph(self.graph, 'nodes')
        self.assertEqual(self.calls, [])

    def test_replacing_both_backend_fields_cannot_rebind_existing_writer(self):
        from kag.backend_identity import BackendIdentitySession
        old = self.config.backend_session
        new = BackendIdentitySession(old._project_client, old._verifier, old._transport,
            project_id=37, project_name=self.config.project_name, namespace=self.config.namespace,
            openspg_endpoint=self.config.host_addr)
        self.addCleanup(new.close)
        proof = new.prove()
        object.__setattr__(self.config, 'backend_session', new)
        object.__setattr__(self.config, 'backend_proof', proof)
        with self.assertRaises(ValueError): self.writer.invoke(self.graph)
        self.assertEqual(self.calls, [])

    def test_mutating_nested_sdk_route_blocks_before_capture(self):
        api = self.writer.client._rest_client.api_client
        original = api.configuration.host
        api.configuration.host = 'http://other-server:8887'
        with self.assertRaises(ValueError): self.writer.invoke(self.graph)
        api.configuration.host = original
        api.url_prefix = '/unapproved'
        with self.assertRaises(ValueError): self.writer.invoke(self.graph)
        self.assertEqual(self.calls, [])

    def test_swapping_upstream_project_config_or_id_blocks_before_capture(self):
        from types import SimpleNamespace
        self.writer.kag_project_config = SimpleNamespace(namespace='Wrong')
        with self.assertRaises(ValueError): self.writer.invoke(self.graph)
        self.writer.kag_project_config = self.config
        self.writer.project_id = 38
        with self.assertRaises(ValueError): self.writer.invoke(self.graph)
        self.assertEqual(self.calls, [])
