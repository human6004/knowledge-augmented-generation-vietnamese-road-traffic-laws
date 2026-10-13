import assert from 'node:assert/strict'
import { test, beforeEach } from 'node:test'
import { loadKagStatus, runRetrieval, inspectionError, loadPipelineStatus, loadBenchmarkDatasets, loadSampleInspection } from '../src/pages/server/kag-inspection.ts'
import { ApiError, tokenKey } from '../src/api.ts'

let calls, tokens
const failure = { state: 'NOT_READY', httpStatus: 503, code: 'NOT_READY' }
const status = { liveness: { state: 'ALIVE', httpStatus: 200 }, queryReadiness: failure, retrievalReadiness: failure, vectorRetrievalReadiness: failure, release: { state: 'RELEASE_UNAVAILABLE', httpStatus: 503 } }
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
const sample = {
  contract_version: 'h1-sample-inspection-1.0', release_id: 'fixture-release', release_kind: 'SAMPLE', source_snapshot_id: 'fixture-source', source_catalog_sha256: 'a'.repeat(64), schema_contract: result.schema_contract, graph_fingerprint: 'b'.repeat(64),
  backend: { database: 'vietroadtraffic', namespace: 'VietRoadTraffic', database_id: 'fixture-db', server_id: 'fixture-server', read_only: true, verified: true },
  counts: { nodes: 1, edges: 0, vectors: 1 }, nodes: [{ entity_type: 'VietRoadTraffic.LegalDocument', entity_id: 'fixture-doc', properties: { id: 'fixture-doc', name: 'fixture-doc', title: 'TEST ONLY' }, sources: [{ evidence_id: 'c'.repeat(64), field: 'title', source_sha256: 'd'.repeat(64) }] }], edges: [],
  verified_at: '2026-10-11T00:00:00+00:00', execution_allowed: false, production_write: 'BLOCKED', sample_receipt: { stage: 'GRAPH_VERIFIED', sealed_at: '2026-10-11T00:00:00Z', receipt_sha256: 'e'.repeat(64), build_run_id: null, progress: null },
  datasets: { ...benchmark, datasets: [] }, providers: { state: 'NOT_CONFIGURED', attempts: null, receipt_window: null, configured_chat_model: null, configured_embedding_model: null, policy_response_version: null, exact_backend_identity_verified: false, upstream_attempts: null, proxy_retries: null }
}

test('dataset metadata exposes version and validated categories with consistent counts', async () => {
  const row = { ...benchmark.datasets[0], eligible_count: 1, ineligible_count: 0, invalid_count: 0, gold_count: 1, missing_gold: { document: [], unit: [], sign: [] }, eligibility_scope: 'G1_RETRIEVAL_GOLD_COVERAGE', metadata: { dataset_version: 'fixture-v2', category_counts: { definition: 1 }, generation_method: null } }
  const body = { ...sample, datasets: { ...benchmark, datasets: [row] } }
  wire(body); assert.equal((await loadSampleInspection()).datasets.datasets[0].metadata.dataset_version, 'fixture-v2')
  for (const metadata of [{ ...row.metadata, category_counts: { definition: 2 } }, { ...row.metadata, dataset_version: '' }, { ...row.metadata, generation_method: 'fabricated' }]) {
    wire({ ...body, datasets: { ...body.datasets, datasets: [{ ...row, metadata }] } }); await assert.rejects(loadSampleInspection())
  }
})
test('sample inspection preserves bounded actual nodes, provenance and separate authority', async () => {
  wire(sample); assert.deepEqual(await loadSampleInspection(), sample); assert.equal(calls[0].url, '/api/admin/kag/sample')
  assert.equal((await loadSampleInspection()).nodes[0].properties.title, 'TEST ONLY')
})
test('sample inspection rejects false proof, fabricated counts, dangling edges and production authority', async () => {
  for (const body of [{ ...sample, backend: { ...sample.backend, verified: false } }, { ...sample, counts: { ...sample.counts, nodes: 2 } },
    { ...sample, execution_allowed: true }, { ...sample, providers: { ...sample.providers, exact_backend_identity_verified: true } },
    { ...sample, counts: { ...sample.counts, edges: 1 }, edges: [{ from: ['VietRoadTraffic.LegalDocument', 'fixture-doc'], predicate: 'hasUnit', to: ['VietRoadTraffic.LegalUnit', 'missing'], properties: {} }] }]) {
    wire(body); await assert.rejects(loadSampleInspection())
  }
})

test('provisional smoke results remain separate from official benchmark authority', async () => {
  const smoke = { state: 'AVAILABLE', review_status: 'PROVISIONAL', g1_eligible_count: 1, graph_fingerprint: sample.graph_fingerprint, official_benchmark: false, runs: { G1: { status: 'COMPLETE', started_at: '2026-10-11T00:00:00Z', finished_at: '2026-10-11T00:01:00Z', requested_count: 1, attempted_count: 1, failed_count: 0, ineligible_count: 0, metrics: { 'unit.Hit@1': { value: 0, scored_count: 1, eligible_count: 1, excluded_count: 0, failed_count: 0, status_counts: { OK: 1, NOT_APPLICABLE: 0, UNAVAILABLE: 0, UNKNOWN: 0 } } }, latency_ms: { successful: { count: 1, min: 10, mean: 10, median: 10, p95: 10, max: 10 }, all_attempted: { count: 1, min: 10, mean: 10, median: 10, p95: 10, max: 10 } } }, G2: null } }
  const row = { ...benchmark.datasets[0], dataset_status: 'PROVISIONAL', dataset_eligibility: 'BLOCKED', reason: 'PROVISIONAL_DATASET', eligible_count: 0, ineligible_count: 1, invalid_count: 0, gold_count: 1, missing_gold: { document: [], unit: [], sign: [] }, eligibility_scope: 'G1_RETRIEVAL_GOLD_COVERAGE', smoke }
  const body = { ...sample, datasets: { ...benchmark, datasets: [row] } }
  wire(body); assert.equal((await loadSampleInspection()).datasets.datasets[0].smoke.runs.G1.metrics['unit.Hit@1'].value, 0)
  for (const change of [{ official_benchmark: true }, { review_status: 'HUMAN_REVIEWED' }, { graph_fingerprint: '0'.repeat(64) }, { state: 'NOT_RUN' }, { runs: { ...smoke.runs, G1: { ...smoke.runs.G1, attempted_count: 2 } } }]) {
    wire({ ...body, datasets: { ...body.datasets, datasets: [{ ...row, smoke: { ...smoke, ...change } }] } }); await assert.rejects(loadSampleInspection())
  }
  const frozenRun = { ...smoke.runs.G1, requested_count: 5, attempted_count: 5, metrics: {}, latency_ms: Object.fromEntries(Object.entries(smoke.runs.G1.latency_ms).map(([k,v])=>[k,{...v,count:5}])) }
  frozenRun.configuration = { protocol_version:'1.0',eval_version:'1.0',metric_policy_version:'1.1',ks:[1],top_k:1,expand:false,rank_semantics:'channel_projected_returned_top_k',identity_catalog_hash:null,release_id:sample.release_id,judge_config:{name:'fixture',version:'v1',model:'synthetic',prompt_version:'p1',temperature:0,seed:null,calibrated:false} }
  const frozenRow = { ...row, dataset_status:'FROZEN',dataset_eligibility:'ELIGIBLE',reason:null,record_count:5,eligible_count:5,ineligible_count:0,gold_count:5,smoke:{...smoke,review_status:'FROZEN',g1_eligible_count:5,runs:{G1:frozenRun,G2:null}} }
  wire({...body,datasets:{...body.datasets,datasets:[frozenRow]}});assert.equal((await loadSampleInspection()).datasets.datasets[0].smoke.runs.G1.requested_count,5)
  for (const changes of [{review_status:'PROVISIONAL'},{official_benchmark:true}]) {
    wire({...body,datasets:{...body.datasets,datasets:[{...frozenRow,smoke:{...frozenRow.smoke,...changes}}]}});await assert.rejects(loadSampleInspection())
  }
})
