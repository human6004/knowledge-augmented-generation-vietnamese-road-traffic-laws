import assert from 'node:assert/strict'
import { test, beforeEach } from 'node:test'
import { loadKagStatus, runRetrieval, inspectionError, loadPipelineStatus, loadBenchmarkDatasets } from '../src/pages/server/kag-inspection.ts'
import { ApiError, tokenKey } from '../src/api.ts'

let calls, tokens
const failure = { state: 'NOT_READY', httpStatus: 503, code: 'NOT_READY' }
const status = { liveness: { state: 'ALIVE', httpStatus: 200 }, queryReadiness: failure, retrievalReadiness: failure, release: { state: 'RELEASE_UNAVAILABLE', httpStatus: 503 } }
const result = { contract_version: 'h1-read-v1.1', request_id: '00000000-0000-4000-8000-000000000001', release_id: 'synthetic-release', source_snapshot_id: 'synthetic-source', schema_contract: { namespace: 'VietRoadTraffic', schema_sha256: 'a'.repeat(64), contract_sha256: 'b'.repeat(64) }, items: [{ entity_type: 'VietRoadTraffic.LegalUnit', entity_id: 'test::1', doc_id: 'test', unit_id: 'test::1', sign_id: null, source_texts: { text: 'TEST ONLY — nguồn thử, không phải căn cứ pháp luật.' }, score: 0.5, vector_sources: [{ property: 'text', score: 0.5, index: 'synthetic-index' }], graph_context: [] }] }
beforeEach(() => {
  calls = []; tokens = new Map([[tokenKey, 'webapp-jwt-fixture']])
  globalThis.sessionStorage = { getItem: key => tokens.get(key), removeItem: key => tokens.delete(key) }
  globalThis.window = { dispatchEvent() {} }
})
function wire(body, code = 200) {
  globalThis.fetch = async (url, options) => {
    calls.push({ url, ...options }); assert.equal(options.headers.get('Authorization'), 'Bearer webapp-jwt-fixture')
    return new Response(JSON.stringify(body), { status: code })
  }
}
test('status uses backend only and keeps ALIVE separate from NOT_READY', async () => {
  wire(status); assert.deepEqual(await loadKagStatus(), status); assert.equal(calls[0].url, '/api/admin/kag/status')
})
test('retrieval preserves evidence and sends no service identity or token', async () => {
  wire(result); assert.deepEqual(await runRetrieval('Nguồn thử 🚦', 3, true), result)
  assert.equal(calls[0].url, '/api/admin/kag/retrieve'); assert.deepEqual(JSON.parse(calls[0].body), { message: 'Nguồn thử 🚦', top_k: 3, expand: true })
})
test('empty evidence remains empty without sample sources', async () => {
  wire({ ...result, items: [] }); assert.deepEqual((await runRetrieval('Nguồn thử', 1, false)).items, [])
})
test('503 never becomes retrieval success or invalidates WebApp session', async () => {
  wire({ message: 'reflected-secret /private/credentials' }, 503)
  await assert.rejects(runRetrieval('Nguồn thử', 1, false), e => e.status === 503 && !inspectionError(e).includes('reflected-secret'))
  assert.equal(tokens.has(tokenKey), true); assert.match(inspectionError(new ApiError('unsafe', 503)), /chưa khả dụng/)
})
test('offline and expired JWT have separate safe errors', async () => {
  globalThis.fetch = async () => { throw Error('unsafe') }; await assert.rejects(loadKagStatus(), e => /Không kết nối/.test(inspectionError(e)))
  wire({}, 401); await assert.rejects(loadKagStatus(), e => /đăng nhập/.test(inspectionError(e))); assert.equal(tokens.has(tokenKey), false)
})
test('USER denial and validation failure remain errors', async () => {
  for (const code of [403, 422]) { wire({ message: 'unsafe' }, code); await assert.rejects(runRetrieval('Nguồn thử', 1, false), e => e.status === code && !inspectionError(e).includes('unsafe')) }
})
test('bad retrieval input makes no request', async () => {
  wire(result); for (const args of [['', 1, false], ['x'.repeat(4001), 1, false], ['Nguồn thử', 0, false], ['Nguồn thử', 11, false], ['Nguồn thử', 1.5, false]]) await assert.rejects(runRetrieval(...args)); assert.equal(calls.length, 0)
})
test('fake answer or malformed evidence fails closed', async () => {
  for (const body of [{ answer: 'fake', citations: [] }, { ...result, items: [{}] }, { ...result, answer: 'fake' }]) { wire(body); await assert.rejects(runRetrieval('Nguồn thử', 1, false)) }
})
test('liveness 200 cannot be used as a readiness proof', async () => {
  wire({ ...status, queryReadiness: { state: 'READY', httpStatus: 200, evidence: { status: 'alive' } } }); await assert.rejects(loadKagStatus())
})
test('artifact-only release cannot claim verified readiness', async () => {
  wire({ ...status, release: { state: 'READY', httpStatus: 200, evidence: { backend_identity_verified: false, source_identity_verified: false, query_ready: false } } }); await assert.rejects(loadKagStatus())
})
test('liveness is never displayed as verified capability readiness', async () => {
  wire({ ...status, liveness: { state: 'READY', httpStatus: 200, evidence: { status: 'ready', capability: 'retrieve', checks: { auth: 'pass', runtime: 'pass', sources: 'pass', admission: 'pass' } } } }); await assert.rejects(loadKagStatus())
})
const pipeline = { contract_version: 'h1-inspect-v1.0', phase: 'idle', active_requests: 0, draining: false, closed: false, progress: null, execution_allowed: false, operational_proof: 'DENY', production_write: 'BLOCKED', provider_egress: 'DENY' }
const benchmark = { contract_version: 'h1-inspect-v1.0', state: 'AVAILABLE', datasets: [{ id: 'synthetic/eval_questions.jsonl', dataset_status: 'FROZEN', dataset_eligibility: 'ELIGIBLE', reason: null, dataset_hash: 'a'.repeat(64), record_count: 1, official_benchmark: false }], execution_allowed: false, execution_blockers: ['OPERATIONAL_PROOF_REQUIRED', 'BENCHMARK_EXECUTION_NOT_AUTHORIZED'], metrics: null }
test('pipeline displays only measured slot state with no fabricated progress', async () => {
  wire(pipeline); assert.deepEqual(await loadPipelineStatus(), pipeline); assert.equal(calls[0].url, '/api/admin/kag/pipeline')
  wire({ ...pipeline, phase: 'running', active_requests: 1 }); assert.equal((await loadPipelineStatus()).phase, 'running')
  for (const body of [{ ...pipeline, progress: 100 }, { ...pipeline, execution_allowed: true }, { ...pipeline, phase: 'running' }, { ...pipeline, provider_egress: 'ALLOW' }]) { wire(body); await assert.rejects(loadPipelineStatus()) }
})
test('frozen dataset eligibility does not grant benchmark execution or invent metrics', async () => {
  wire(benchmark); const value = await loadBenchmarkDatasets(); assert.deepEqual(value, benchmark); assert.equal(value.execution_allowed, false); assert.equal(value.metrics, null); assert.equal(calls[0].url, '/api/admin/kag/benchmark/datasets')
  for (const body of [{ ...benchmark, metrics: { accuracy: 1 } }, { ...benchmark, execution_allowed: true }, { ...benchmark, datasets: [{ ...benchmark.datasets[0], dataset_status: 'PROVISIONAL' }] }]) { wire(body); await assert.rejects(loadBenchmarkDatasets()) }
})
test('inspection offline and 503 do not turn into idle or eligible success', async () => {
  wire({}, 503); await assert.rejects(loadPipelineStatus()); await assert.rejects(loadBenchmarkDatasets())
  globalThis.fetch = async () => { throw Error('offline') }; await assert.rejects(loadPipelineStatus())
})
test('inspection rejects unexpected fields, unsafe IDs and incomplete execution blockers', async () => {
  wire({ ...pipeline, credential: 'unexpected' }); await assert.rejects(loadPipelineStatus())
  for (const body of [{ ...benchmark, execution_blockers: [] }, { ...benchmark, credential: 'unexpected' },
    { ...benchmark, datasets: [{ ...benchmark.datasets[0], id: '../private/file' }] },
    { ...benchmark, datasets: [{ ...benchmark.datasets[0], dataset_hash: 'unverified' }] },
    { ...benchmark, datasets: [benchmark.datasets[0], benchmark.datasets[0]] }]) {
    wire(body); await assert.rejects(loadBenchmarkDatasets())
  }
})
