"""Offline transport fixtures; no provider calls or credentials."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import httpx
from tenacity import retry, stop_after_attempt


class ProviderBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'attempts.json'
        self.module = importlib.import_module('kag.http_api.provider_budget')

    def budget(self):
        return self.module.ProviderBudget(self.path,
            embedding_url='https://embedding.invalid/v1/embeddings',
            embedding_model='fixture-embedding',
            chat_url='https://chat.invalid/v1/chat/completions', chat_model='fixture-chat')

    def request(self, kind='chat', **kwargs):
        endpoint = 'https://chat.invalid/v1/chat/completions' if kind=='chat' else 'https://embedding.invalid/v1/embeddings'
        return httpx.Request('POST', kwargs.get('url',endpoint),
            json={'model':kwargs.get('model','fixture-'+kind), 'input':'fixture'})

    def test_shared_instances_count_failure_timeout_and_success_before_send(self):
        budget = self.budget()
        seen = []
        def send(request):
            seen.append(self.budget().counts()['chat'])
            if len(seen)==1: raise httpx.ReadTimeout('fixture',request=request)
            return httpx.Response(500 if len(seen)==2 else 200)
        guard = budget.guard_sync('chat',httpx.MockTransport(send))
        with self.assertRaises(httpx.ReadTimeout): guard.handle_request(self.request())
        self.assertEqual(guard.handle_request(self.request()).status_code,500)
        self.assertEqual(guard.handle_request(self.request()).status_code,200)
        with self.assertRaises(self.module.BudgetError):
            self.budget().guard_sync('chat',httpx.MockTransport(send)).handle_request(self.request())
        self.assertEqual(seen,[1,2,3])
        self.assertEqual(budget.counts(),{'chat':3,'embedding':0})

    def test_concurrent_instances_reserve_only_three(self):
        def reserve(_):
            try: return self.budget().reserve('embedding')
            except self.module.BudgetError: return None
        with ThreadPoolExecutor(max_workers=12) as pool:
            values=list(pool.map(reserve,range(24)))
        self.assertEqual(sorted(x for x in values if x is not None),[1,2,3])
        self.assertEqual(self.budget().counts()['embedding'],3)

    def test_wrong_url_or_model_denied_without_attempt(self):
        sent=[]; budget=self.budget()
        guard=budget.guard_sync('chat',httpx.MockTransport(lambda r: sent.append(r)))
        for request in (self.request(url='https://other.invalid/v1/chat/completions'),
                        self.request(url='https://chat.invalid/v1/chat/completions?x=1'),
                        self.request(model='other-model')):
            with self.assertRaises(self.module.BudgetError): guard.handle_request(request)
        self.assertEqual(sent,[])
        self.assertEqual(budget.counts(),{'chat':0,'embedding':0})

    def test_duplicate_model_keys_denied_without_attempt(self):
        budget=self.budget(); seen=[]
        guard=budget.guard_sync('chat',httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200)))
        request=httpx.Request('POST','https://chat.invalid/v1/chat/completions',
            content=b'{"model":"other","model":"fixture-chat"}')
        with self.assertRaises(self.module.BudgetError): guard.handle_request(request)
        self.assertEqual(seen,[])
        self.assertEqual(budget.counts()['chat'],0)

    def test_deleted_ledger_does_not_reset_consumed_attempts(self):
        self.budget().reserve('chat')
        self.path.unlink()
        with self.assertRaises(self.module.BudgetError): self.budget().reserve('chat')
        self.assertFalse(self.path.exists())

    def test_redirect_denied_and_counted_once(self):
        budget=self.budget(); sent=[]
        def reply(r):
            sent.append(r)
            return httpx.Response(307,headers={'location':'https://other.invalid/'})
        with httpx.Client(transport=budget.guard_sync('chat',httpx.MockTransport(reply)),follow_redirects=True) as client:
            with self.assertRaises(self.module.BudgetError): client.send(self.request())
        self.assertEqual(len(sent),1)
        self.assertEqual(budget.counts()['chat'],1)

    def test_async_failures_share_the_sync_cap(self):
        budget=self.budget(); seen=[]
        async def send(request):
            seen.append(budget.counts()['embedding'])
            raise httpx.ConnectTimeout('fixture',request=request)
        async def run():
            guard=budget.guard_async('embedding',httpx.MockTransport(send))
            for _ in range(3):
                with self.assertRaises(httpx.ConnectTimeout):
                    await guard.handle_async_request(self.request('embedding'))
            with self.assertRaises(self.module.BudgetError):
                await guard.handle_async_request(self.request('embedding'))
            await guard.aclose()
        asyncio.run(run())
        self.assertEqual(seen,[1,2,3])
        self.assertEqual(self.budget().counts()['embedding'],3)

    def test_corrupt_or_different_binding_never_resets_ledger(self):
        budget=self.budget(); budget.reserve('chat')
        original=self.path.read_bytes()
        with self.assertRaises(self.module.BudgetError):
            self.module.ProviderBudget(self.path,embedding_url='https://embedding.invalid/v1/embeddings',
                embedding_model='other',chat_url='https://chat.invalid/v1/chat/completions',
                chat_model='fixture-chat').reserve('chat')
        self.assertEqual(self.path.read_bytes(),original)
        self.path.write_text('{broken',encoding='utf-8')
        with self.assertRaises(self.module.BudgetError): budget.reserve('chat')
        self.assertEqual(self.path.read_text(encoding='utf-8'),'{broken')

    def test_configure_both_sdk_clients_disables_retry_and_redirect(self):
        budget=self.budget()
        model=SimpleNamespace(client=SimpleNamespace(_client=httpx.Client(),max_retries=2),
                              aclient=SimpleNamespace(_client=httpx.AsyncClient(),max_retries=2))
        budget.configure_sdk(model,'chat')
        for sdk in (model.client,model.aclient):
            self.assertEqual(sdk.max_retries,0)
            self.assertFalse(sdk._client.follow_redirects)
        model.client._client.close()
        asyncio.run(model.aclient._client.aclose())

    def test_real_sdk_failure_has_one_sync_and_one_async_attempt(self):
        from openai import OpenAI, AsyncOpenAI, APIStatusError
        budget=self.budget(); seen=[]
        def reply(request):
            seen.append(budget.counts()['chat'])
            return httpx.Response(500,json={'error':{'message':'offline fixture'}})
        model=SimpleNamespace(
            client=OpenAI(api_key='offline-fixture',base_url='https://chat.invalid/v1',
                http_client=httpx.Client(transport=httpx.MockTransport(reply))),
            aclient=AsyncOpenAI(api_key='offline-fixture',base_url='https://chat.invalid/v1',
                http_client=httpx.AsyncClient(transport=httpx.MockTransport(reply))))
        budget.configure_sdk(model,'chat')
        try:
            with self.assertRaises(APIStatusError):
                model.client.chat.completions.create(model='fixture-chat',messages=[])
            async def run():
                with self.assertRaises(APIStatusError):
                    await model.aclient.chat.completions.create(model='fixture-chat',messages=[])
            asyncio.run(run())
            self.assertEqual(seen,[1,2])
            self.assertEqual(budget.counts()['chat'],2)
        finally:
            model.client.close()
            asyncio.run(model.aclient.close())

    def test_instance_retry_removal_keeps_pipeline_five_and_other_instances(self):
        class Pipeline:
            max_iteration=5
            @retry(stop=stop_after_attempt(3),reraise=True)
            async def planning(self):
                self.calls+=1
                raise ValueError('fixture')
            def __init__(self): self.calls=0
        class LLM:
            @retry(stop=stop_after_attempt(3),reraise=True)
            def call_with_json_parse(self):
                self.calls+=1
                raise ValueError('fixture')
            @retry(stop=stop_after_attempt(3),reraise=True)
            async def acall_with_json_parse(self):
                self.calls+=1
                raise ValueError('fixture')
            def __init__(self): self.calls=0
        pipeline,llm=Pipeline(),LLM()
        self.module.disable_instance_retries(pipeline,llm)
        with self.assertRaises(ValueError): asyncio.run(pipeline.planning())
        with self.assertRaises(ValueError): llm.call_with_json_parse()
        with self.assertRaises(ValueError): asyncio.run(llm.acall_with_json_parse())
        self.assertEqual((pipeline.calls,llm.calls,pipeline.max_iteration),(1,2,5))
        other=LLM()
        with self.assertRaises(ValueError): other.call_with_json_parse()
        self.assertEqual(other.calls,3)

    def test_pinned_upstream_methods_support_instance_only_unwrapping(self):
        from kag.common.llm.openai_client import OpenAIClient
        from kag.solver.pipeline.kag_iterative_pipeline import KAGIterativePipeline
        pipeline=object.__new__(KAGIterativePipeline)
        pipeline.max_iteration=5
        llm=object.__new__(OpenAIClient)
        originals={name:getattr(OpenAIClient,name) for name in ('call_with_json_parse','acall_with_json_parse')}
        planning=KAGIterativePipeline.planning
        self.module.disable_instance_retries(pipeline,llm)
        self.assertIs(pipeline.planning.__func__,planning.__wrapped__)
        self.assertEqual(pipeline.max_iteration,5)
        self.assertIs(KAGIterativePipeline.planning,planning)
        for name,original in originals.items():
            self.assertIs(getattr(llm,name).__func__,original.__wrapped__)
            self.assertIs(getattr(OpenAIClient,name),original)


if __name__=='__main__': unittest.main()
