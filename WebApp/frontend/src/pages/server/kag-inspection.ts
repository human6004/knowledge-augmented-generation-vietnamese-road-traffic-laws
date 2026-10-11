import { api, send, ApiError } from '../../api.ts'

export type KagCheck = { state: 'ALIVE' | 'READY' | 'NOT_READY' | 'UNAVAILABLE' | 'NOT_CONFIGURED' | 'RELEASE_UNAVAILABLE'; httpStatus: number; code?: string; evidence?: Record<string, unknown> }
export type KagStatus = Record<'liveness' | 'queryReadiness' | 'retrievalReadiness' | 'release', KagCheck>
export type Retrieval = { contract_version: string; request_id: string; release_id: string; source_snapshot_id: string; schema_contract: Record<string, string>; items: { entity_type: string; entity_id: string; doc_id: string | null; unit_id: string | null; sign_id: string | null; source_texts: Record<string, string | null>; score: number | null; vector_sources: unknown[]; graph_context: unknown[] }[] }
export type PipelineStatus = { contract_version: string; phase: 'idle' | 'running' | 'draining' | 'closed' | 'unavailable'; active_requests: number | null; draining: boolean | null; closed: boolean | null; progress: null; execution_allowed: false; operational_proof: 'DENY'; production_write: 'BLOCKED'; provider_egress: 'DENY' }
export type BenchmarkDatasets = { contract_version: string; state: 'AVAILABLE' | 'NOT_CONFIGURED' | 'UNAVAILABLE' | 'LIMIT_EXCEEDED'; datasets: { id: string; dataset_status: 'FROZEN' | 'PROVISIONAL' | null; dataset_eligibility: 'ELIGIBLE' | 'BLOCKED'; reason: string | null; dataset_hash: string | null; record_count: number | null; official_benchmark: boolean }[]; execution_allowed: false; execution_blockers: string[]; metrics: null }
const states = ['ALIVE', 'READY', 'NOT_READY', 'UNAVAILABLE', 'NOT_CONFIGURED', 'RELEASE_UNAVAILABLE']
export function inspectionError(error: unknown) {
  const status = error instanceof ApiError ? error.status : -1
  return status === 401 ? 'Phiên đã hết hạn. Vui lòng đăng nhập lại.' : status === 403 ? 'Chỉ ADMIN được sử dụng chức năng này.' : status === 422 || status === 400 ? 'Yêu cầu truy xuất không hợp lệ.' : status === 0 ? 'Không kết nối được backend. Hãy thử lại.' : status === 503 ? 'Truy xuất KAG chưa khả dụng hoặc thiếu cấu hình dịch vụ.' : 'Phản hồi KAG chưa đủ bằng chứng hoặc không hợp lệ.'
}
export async function loadKagStatus(signal?: AbortSignal): Promise<KagStatus> {
  const result = await api<KagStatus>('/admin/kag/status', { signal })
  if (!result || Object.keys(result).sort().join() !== ['liveness', 'queryReadiness', 'retrievalReadiness', 'release'].sort().join()) throw new ApiError('Invalid KAG status', 502)
  for (const [key, check] of Object.entries(result)) {
    if (!check || !states.includes(check.state) || !Number.isInteger(check.httpStatus)) throw new ApiError('Invalid KAG status', 502)
    if (check.state === 'ALIVE' && key !== 'liveness') throw new ApiError('Liveness is not readiness', 502)
    if (check.state === 'READY') {
      if (key === 'liveness') throw new ApiError('Liveness is not readiness', 502)
      const evidence = check.evidence
      const verified = key === 'release' ? evidence?.backend_identity_verified === true && evidence?.source_identity_verified === true && evidence?.query_ready === true : evidence?.status === 'ready' && evidence?.capability === (key === 'queryReadiness' ? 'query-v1' : 'retrieve') && ['auth', 'runtime', 'sources', 'admission'].every(field => (evidence?.checks as Record<string, string>)?.[field] === 'pass')
      if (check.httpStatus !== 200 || !verified) throw new ApiError('Unverified readiness', 502)
    }
  }
  return result
}
export async function runRetrieval(message: string, top_k: number, expand: boolean): Promise<Retrieval> {
  if (!message.trim() || message.length > 4000 || !Number.isInteger(top_k) || top_k < 1 || top_k > 10 || typeof expand !== 'boolean') throw new ApiError('Invalid request', 422)
  const value = await api<Retrieval>('/admin/kag/retrieve', send('POST', { message, top_k, expand }))
  if (!value || Object.keys(value).sort().join() !== ['contract_version', 'request_id', 'release_id', 'source_snapshot_id', 'schema_contract', 'items'].sort().join() || value.contract_version !== 'h1-read-v1.1' ||
    typeof value.request_id !== 'string' || typeof value.release_id !== 'string' || !value.release_id || typeof value.source_snapshot_id !== 'string' || !value.source_snapshot_id || !value.schema_contract ||
    !Array.isArray(value.items) || value.items.length > 110) throw new ApiError('Invalid retrieval', 502)
  for (const item of value.items) {
    if (!item || Object.keys(item).sort().join() !== ['entity_type', 'entity_id', 'doc_id', 'unit_id', 'sign_id', 'source_texts', 'score', 'vector_sources', 'graph_context'].sort().join() ||
      typeof item.entity_type !== 'string' || !item.entity_type || typeof item.entity_id !== 'string' || !item.entity_id || !item.source_texts || typeof item.source_texts !== 'object' || Array.isArray(item.source_texts) ||
      Object.values(item.source_texts).some(text => text !== null && typeof text !== 'string') || !Array.isArray(item.vector_sources) || !Array.isArray(item.graph_context) ||
      (item.score !== null && (!Number.isFinite(item.score) || item.score < 0 || item.score > 1))) throw new ApiError('Invalid evidence', 502)
  }
  return value
}
export async function loadPipelineStatus(signal?: AbortSignal): Promise<PipelineStatus> {
  const value = await api<PipelineStatus>('/admin/kag/pipeline', { signal })
  if (!value || Object.keys(value).sort().join() !== ['contract_version', 'phase', 'active_requests', 'draining', 'closed', 'progress', 'execution_allowed', 'operational_proof', 'production_write', 'provider_egress'].sort().join() || value.contract_version !== 'h1-inspect-v1.0' || value.progress !== null || value.execution_allowed !== false || value.operational_proof !== 'DENY' || value.production_write !== 'BLOCKED' || value.provider_egress !== 'DENY') throw new ApiError('Invalid pipeline proof', 502)
  if (value.phase === 'unavailable') {
    if (value.active_requests !== null || value.closed !== null || value.draining !== null) throw new ApiError('Invalid unavailable runtime', 502)
  } else {
    if (![0, 1].includes(value.active_requests as number) || typeof value.closed !== 'boolean' || typeof value.draining !== 'boolean' || value.phase !== (value.closed ? 'closed' : value.draining ? 'draining' : value.active_requests === 1 ? 'running' : 'idle')) throw new ApiError('Invalid runtime state', 502)
  }
  return value
}
export async function loadBenchmarkDatasets(signal?: AbortSignal): Promise<BenchmarkDatasets> {
  const value = await api<BenchmarkDatasets>('/admin/kag/benchmark/datasets', { signal })
  if (!value || Object.keys(value).sort().join() !== ['contract_version', 'state', 'datasets', 'execution_allowed', 'execution_blockers', 'metrics'].sort().join() || value.contract_version !== 'h1-inspect-v1.0' || value.execution_allowed !== false || value.metrics !== null || !Array.isArray(value.execution_blockers) || value.execution_blockers.join() !== 'OPERATIONAL_PROOF_REQUIRED,BENCHMARK_EXECUTION_NOT_AUTHORIZED' || !['AVAILABLE', 'NOT_CONFIGURED', 'UNAVAILABLE', 'LIMIT_EXCEEDED'].includes(value.state) || !Array.isArray(value.datasets) || value.datasets.length > 20 || (value.state !== 'AVAILABLE' && value.datasets.length)) throw new ApiError('Invalid benchmark proof', 502)
  const seen = new Set<string>()
  for (const row of value.datasets) {
    if (!row || Object.keys(row).sort().join() !== ['id', 'dataset_status', 'dataset_eligibility', 'reason', 'dataset_hash', 'record_count', 'official_benchmark'].sort().join() || typeof row.id !== 'string' || !/^[A-Za-z0-9_.-]{1,128}(?:\/eval_questions\.jsonl)?$/.test(row.id) || row.id.startsWith('../') || seen.has(row.id) || !['ELIGIBLE', 'BLOCKED'].includes(row.dataset_eligibility) || typeof row.official_benchmark !== 'boolean' ||
      (row.dataset_status !== null && !['FROZEN', 'PROVISIONAL'].includes(row.dataset_status)) || (row.dataset_hash !== null && (typeof row.dataset_hash !== 'string' || !/^[0-9a-f]{64}$/.test(row.dataset_hash))) || (row.record_count !== null && (!Number.isInteger(row.record_count) || row.record_count < 1)) || (row.official_benchmark && row.dataset_status !== 'FROZEN') ||
      (row.dataset_eligibility === 'BLOCKED' && !['PROVISIONAL_DATASET', 'NO_GOLD', 'INVALID_DATASET', 'DATASET_TOO_LARGE'].includes(row.reason as string)) ||
      (row.dataset_eligibility === 'ELIGIBLE' && (row.dataset_status !== 'FROZEN' || !row.dataset_hash || !Number.isInteger(row.record_count) || (row.record_count as number) < 1 || row.reason !== null))) throw new ApiError('Invalid dataset proof', 502)
    seen.add(row.id)
  }
  return value
}
