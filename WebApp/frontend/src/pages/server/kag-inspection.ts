import { api, send, ApiError } from '../../api.ts'

export type KagCheck = { state: 'ALIVE' | 'READY' | 'NOT_READY' | 'UNAVAILABLE' | 'NOT_CONFIGURED' | 'RELEASE_UNAVAILABLE'; httpStatus: number; code?: string; evidence?: Record<string, unknown> }
export type KagStatus = Record<'liveness' | 'queryReadiness' | 'retrievalReadiness' | 'vectorRetrievalReadiness' | 'release', KagCheck>
export type Retrieval = { contract_version: string; request_id: string; release_id: string; source_snapshot_id: string; schema_contract: Record<string, string>; items: { entity_type: string; entity_id: string; doc_id: string | null; unit_id: string | null; sign_id: string | null; source_texts: Record<string, string | null>; score: number | null; vector_sources: unknown[]; graph_context: unknown[] }[] }
export type PipelineStatus = { contract_version: string; phase: 'idle' | 'running' | 'draining' | 'closed' | 'unavailable'; active_requests: number | null; draining: boolean | null; closed: boolean | null; progress: null; execution_allowed: false; operational_proof: 'DENY'; production_write: 'BLOCKED'; provider_egress: 'DENY' }
export type KagConfiguration = {
  contract_version: 'kag-config-v1'
  project: { source: 'startup_environment'; release_id: string | null; release_state: 'NOT_CONFIGURED' | 'LOADED' | 'UNAVAILABLE' }
  models: { source: 'startup_environment'; identity_verified: false; chat: ModelConfiguration; embedding: ModelConfiguration }
  solver: null | { source: 'source_defaults'; pipeline: 'KAGIterativePipeline'; planner: 'KAGIterativePlanner'; top_k: number; expand: boolean; max_evidence_chars: number; max_iteration: number; search_k: number; expansion_limit: number; required_vector_dimensions: number }
}
type ModelConfiguration = { state: 'CONFIGURED' | 'NOT_CONFIGURED' | 'INCOMPLETE' | 'INVALID'; model: string | null; endpoint: string | null }
export type LLMInput = { provider: 'openai-compatible'; base_url: string; model: string; api_key?: string }
type LLMMetadata = Omit<LLMInput, 'api_key'> & { key_configured: true }
export type LLMCredentials = {
  contract_version: 'llm-credentials-v3'; revision: number; saved: boolean
  chat: LLMMetadata | null; embedding: LLMMetadata | null
  applied: boolean; connection_tested: boolean; save_allowed: boolean
  error_code: 'CONFIG_INVALID' | 'CONFIG_STORAGE_UNAVAILABLE' | null
  roles: Record<'chat' | 'embedding', {
    saved_revision: number | null; active_revision: number | null; active: LLMMetadata | null
    test: null | { revision: number; status: 'PASS' | 'FAIL' | 'BLOCKED'; code: string | null; dimension: number | null; observed_model: string | null; client_attempts: number; output_chars: number; tested_at: string }
    status: 'NOT_CONFIGURED' | 'SAVED' | 'PENDING_APPLY' | 'APPLIED' | 'BLOCKED'; blocker: string | null
    actions: { test: boolean; apply: boolean }
  }>
  build_config: { state: 'NOT_SUPPORTED'; reason: 'BUILDER_REPLAY_ONLY' }
}
function llmInput(value: LLMInput) {
  if (!value || value.provider !== 'openai-compatible' || typeof value.model !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._/:-]{0,199}$/.test(value.model) ||
    typeof value.base_url !== 'string' || value.base_url.length > 2048 || /[\s\x00-\x1f\x7f]/.test(value.base_url)) return false
  try {
    const url = new URL(value.base_url)
    if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password || url.search || url.hash || url.port === '0') return false
  } catch { return false }
  return value.api_key === undefined || typeof value.api_key === 'string' && /^[!-~]{1,4096}$/.test(value.api_key)
}
function validateLLMCredentials(value: LLMCredentials) {
  const invalid = () => { throw new ApiError('Metadata cấu hình model không hợp lệ', 502) }
  if (!shape(value, ['contract_version', 'revision', 'saved', 'chat', 'embedding', 'applied', 'connection_tested', 'save_allowed', 'error_code', 'roles', 'build_config']) ||
    value.contract_version !== 'llm-credentials-v3' || !count(value.revision, 2147483647) || typeof value.saved !== 'boolean' ||
    typeof value.save_allowed !== 'boolean' || typeof value.applied !== 'boolean' || typeof value.connection_tested !== 'boolean' ||
    !shape(value.roles, ['chat', 'embedding']) || !shape(value.build_config, ['state', 'reason']) ||
    value.build_config.state !== 'NOT_SUPPORTED' || value.build_config.reason !== 'BUILDER_REPLAY_ONLY' ||
    value.error_code !== null && !['CONFIG_INVALID', 'CONFIG_STORAGE_UNAVAILABLE'].includes(value.error_code)) invalid()
  for (const role of ['chat', 'embedding'] as const) {
    const model = value[role]
    if (model !== null && (!shape(model, ['provider', 'base_url', 'model', 'key_configured']) || !llmInput(model) || model.key_configured !== true)) invalid()
    const row = value.roles[role], test = row?.test
    if (!shape(row, ['saved_revision', 'test', 'active_revision', 'active', 'status', 'blocker', 'actions']) ||
      (row.saved_revision === null) !== (model === null) || row.saved_revision !== null && (!count(row.saved_revision, value.revision) || row.saved_revision < 1) ||
      row.active_revision !== null && (!count(row.active_revision, value.revision) || row.active_revision < 1) ||
      row.active !== null && (!shape(row.active, ['provider', 'base_url', 'model', 'key_configured']) || !llmInput(row.active) || row.active.key_configured !== true) ||
      !['NOT_CONFIGURED', 'SAVED', 'PENDING_APPLY', 'APPLIED', 'BLOCKED'].includes(row.status) ||
      row.blocker !== null && !modelErrorCodes.includes(row.blocker) || !shape(row.actions, ['test', 'apply']) ||
      typeof row.actions.test !== 'boolean' || typeof row.actions.apply !== 'boolean') invalid()
    if (test !== null && (!shape(test, ['revision', 'status', 'code', 'dimension', 'observed_model', 'client_attempts', 'output_chars', 'tested_at']) ||
      test.revision !== row.saved_revision || !['PASS', 'FAIL', 'BLOCKED'].includes(test.status) ||
      test.code !== null && !modelErrorCodes.includes(test.code) || (test.status === 'PASS') !== (test.code === null) ||
      !count(test.client_attempts, 1) || !count(test.output_chars, 262144) || test.dimension !== null && !count(test.dimension, 262144) ||
      test.observed_model !== null && (typeof test.observed_model !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._/:-]{0,199}$/.test(test.observed_model)) || typeof test.tested_at !== 'string' ||
      !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00$/.test(test.tested_at) ||
      test.status === 'PASS' && (test.client_attempts !== 1 || (role === 'embedding' ? test.dimension === null || test.dimension < 1 || test.dimension > 65536 : test.output_chars < 1)))) invalid()
    if (row.status === 'APPLIED' && (row.active_revision !== row.saved_revision || JSON.stringify(row.active) !== JSON.stringify(model))) invalid()
  }
  if (value.saved ? value.revision < 1 || value.chat === null && value.embedding === null : value.revision !== 0 || value.chat !== null || value.embedding !== null) invalid()
  if ((value.error_code !== null || value.revision === 2147483647) && value.save_allowed) invalid()
  if (value.applied !== Object.values(value.roles).some(row => row.status === 'APPLIED') ||
    value.connection_tested !== Object.values(value.roles).some(row => row.test?.status === 'PASS')) invalid()
  return value
}
const modelErrorCodes = ['TEST_REQUIRED', 'TEST_IN_PROGRESS', 'RELEASE_UNAVAILABLE', 'RELEASE_MISMATCH', 'VECTOR_IDENTITY_MISMATCH',
  'ACTIVE_CONFIG_INVALID', 'PROXY_POLICY_UNVERIFIED', 'BLOCKED', 'AUTH_FAILED', 'MODEL_NOT_FOUND', 'RATE_LIMITED', 'PROVIDER_ERROR',
  'MODEL_MISMATCH', 'DIMENSION_MISMATCH', 'INVALID_RESPONSE', 'TIMEOUT', 'NETWORK_ERROR']
export async function loadLLMCredentials(signal?: AbortSignal): Promise<LLMCredentials> {
  return validateLLMCredentials(await api<LLMCredentials>('/admin/kag/config/models', { signal, cache: 'no-store' }))
}
export async function saveLLMCredentials(revision: number, role: 'chat' | 'embedding', input: LLMInput): Promise<LLMCredentials> {
  if (!count(revision, 2147483646) || !['chat', 'embedding'].includes(role) || !llmInput(input)) throw new ApiError('Provider, model, Base URL hoặc API key không hợp lệ', 400)
  return validateLLMCredentials(await api<LLMCredentials>('/admin/kag/config/models', send('POST', { revision, [role]: input })))
}
export async function changeLLMModel(role: 'chat' | 'embedding', action: 'test' | 'apply', revision: number): Promise<LLMCredentials> {
  if (!count(revision, 2147483646) || !['chat', 'embedding'].includes(role) || !['test', 'apply'].includes(action)) throw new ApiError('Thao tác model không hợp lệ', 400)
  return validateLLMCredentials(await api<LLMCredentials>(`/admin/kag/config/models/${role}/${action}`, send('POST', { revision })))
}
export type ChatRetrievalValues = { top_k: number; expand: boolean }
export type ChatRetrievalConfiguration = {
  contract_version: 'chat-retrieval-v1'; revision: number
  saved: ChatRetrievalValues | null; active: ChatRetrievalValues | null; previous: ChatRetrievalValues | null
  persisted: boolean; pending: boolean; runtime_idle: boolean
  actions: { save: boolean; apply: boolean; restore: boolean }
  error_code: 'CONFIG_INVALID' | 'CONFIG_STORAGE_UNAVAILABLE' | null
}
function retrievalValues(value: unknown): value is ChatRetrievalValues {
  const v = value as ChatRetrievalValues
  return shape(v, ['top_k', 'expand']) && Number.isInteger(v.top_k) && v.top_k >= 1 && v.top_k <= 10 && typeof v.expand === 'boolean'
}
function validateChatRetrieval(value: ChatRetrievalConfiguration) {
  const invalid = () => { throw new ApiError('Cấu hình Retrieval cho Chat không hợp lệ', 502) }
  if (!shape(value, ['contract_version', 'revision', 'saved', 'active', 'previous', 'persisted', 'pending', 'runtime_idle', 'actions', 'error_code']) ||
    value.contract_version !== 'chat-retrieval-v1' || !count(value.revision, 2147483647) || !shape(value.actions, ['save', 'apply', 'restore']) ||
    typeof value.persisted !== 'boolean' || typeof value.pending !== 'boolean' || typeof value.runtime_idle !== 'boolean' ||
    value.error_code !== null && !['CONFIG_INVALID', 'CONFIG_STORAGE_UNAVAILABLE'].includes(value.error_code) ||
    (value.active === null ? value.saved !== null || value.previous !== null || value.error_code === null : !retrievalValues(value.active) || !retrievalValues(value.saved) || value.previous !== null && !retrievalValues(value.previous)) ||
    value.pending !== (value.active?.top_k !== value.saved?.top_k || value.active?.expand !== value.saved?.expand)) invalid()
  const available = value.active !== null && value.error_code === null && value.revision < 2147483647
  if (value.actions.save !== available || value.actions.apply !== (available && value.runtime_idle && value.pending) || value.actions.restore !== (available && value.runtime_idle && value.previous !== null)) invalid()
  return value
}
export async function loadChatRetrieval(signal?: AbortSignal): Promise<ChatRetrievalConfiguration> {
  return validateChatRetrieval(await api<ChatRetrievalConfiguration>('/admin/kag/config/retrieval', { signal, cache: 'no-store' }))
}
export async function changeChatRetrieval(action: 'save' | 'apply' | 'restore', revision: number, values?: ChatRetrievalValues): Promise<ChatRetrievalConfiguration> {
  if (!['save', 'apply', 'restore'].includes(action) || !count(revision, 2147483646) || (action === 'save' ? !retrievalValues(values) : values !== undefined)) throw new ApiError('Giá trị Retrieval không hợp lệ', 400)
  return validateChatRetrieval(await api<ChatRetrievalConfiguration>(`/admin/kag/config/retrieval/${action}`, send('POST', { revision, ...(values ? { values } : {}) })))
}
export async function loadKagConfiguration(signal?: AbortSignal): Promise<KagConfiguration> {
  const value = await api<KagConfiguration>('/admin/kag/config', { signal, cache: 'no-store' })
  const invalid = () => { throw new ApiError('Thông tin cấu hình KAG không hợp lệ', 502) }
  const optionalText = (v: unknown, pattern: RegExp) => v === null || typeof v === 'string' && pattern.test(v)
  if (!shape(value, ['contract_version', 'project', 'models', 'solver']) || value.contract_version !== 'kag-config-v1' ||
    !shape(value.project, ['source', 'release_id', 'release_state']) || value.project.source !== 'startup_environment' ||
    !['NOT_CONFIGURED', 'LOADED', 'UNAVAILABLE'].includes(value.project.release_state) ||
    !optionalText(value.project.release_id, /^[A-Za-z0-9][A-Za-z0-9_.-]{0,199}$/) || value.project.release_state === 'LOADED' && value.project.release_id === null ||
    !shape(value.models, ['source', 'identity_verified', 'chat', 'embedding']) || value.models.source !== 'startup_environment' || value.models.identity_verified !== false) invalid()
  for (const role of ['chat', 'embedding'] as const) {
    const model = value.models[role]
    if (!shape(model, ['state', 'model', 'endpoint']) || !['CONFIGURED', 'NOT_CONFIGURED', 'INCOMPLETE', 'INVALID'].includes(model.state) ||
      !optionalText(model.model, /^[A-Za-z0-9][A-Za-z0-9._/:-]{0,199}$/) || !optionalText(model.endpoint, /^https?:\/\/[A-Za-z0-9.\[\]:-]{1,260}$/) ||
      model.state === 'CONFIGURED' && (model.model === null || model.endpoint === null) ||
      model.state === 'NOT_CONFIGURED' && (model.model !== null || model.endpoint !== null)) invalid()
  }
  const solver = value.solver
  if (solver !== null && (!shape(solver, ['source', 'pipeline', 'planner', 'top_k', 'expand', 'max_evidence_chars', 'max_iteration', 'search_k', 'expansion_limit', 'required_vector_dimensions']) ||
    solver.source !== 'source_defaults' || solver.pipeline !== 'KAGIterativePipeline' || solver.planner !== 'KAGIterativePlanner' || typeof solver.expand !== 'boolean' ||
    [solver.top_k, solver.max_evidence_chars, solver.max_iteration, solver.search_k, solver.expansion_limit, solver.required_vector_dimensions].some(n => !count(n) || n < 1) || solver.top_k > solver.search_k)) invalid()
  return value
}
export type BuilderState = 'IDLE' | 'RUNNING' | 'STOPPING' | 'STOPPED' | 'COMPLETE' | 'BLOCKED'
export type BuilderStatus = { contract_version: 'builder-control-v1'; state: BuilderState; run_id: string | null; target: { project_id: number; database: string; namespace: 'VietRoadTraffic' } | null; progress: { stage: string; done: number; total: number } | null; error_code: string | null; actions: { build: boolean; stop: boolean; resume: boolean; delete: false }; delete_reason: 'DELETE_NOT_AUTHORIZED'; production_write: 'BLOCKED' }
export function builderStateLabel(state: BuilderState) {
  return { IDLE: 'Chưa build', RUNNING: 'Đang build', STOPPING: 'Đang dừng...', STOPPED: 'Đã dừng an toàn', COMPLETE: 'Hoàn tất', BLOCKED: 'Bị chặn' }[state]
}
function validateBuilder(value: BuilderStatus): BuilderStatus {
  if (!value || Object.keys(value).sort().join() !== ['contract_version', 'state', 'run_id', 'target', 'progress', 'error_code', 'actions', 'delete_reason', 'production_write'].sort().join() ||
    value.contract_version !== 'builder-control-v1' || !['IDLE', 'RUNNING', 'STOPPING', 'STOPPED', 'COMPLETE', 'BLOCKED'].includes(value.state) || value.production_write !== 'BLOCKED' || value.delete_reason !== 'DELETE_NOT_AUTHORIZED' ||
    !value.actions || Object.keys(value.actions).sort().join() !== ['build', 'stop', 'resume', 'delete'].sort().join() ||
    value.actions.build !== ['IDLE', 'COMPLETE'].includes(value.state) || value.actions.stop !== (value.state === 'RUNNING') || value.actions.resume !== (value.state === 'STOPPED') || value.actions.delete !== false ||
    (value.run_id === null ? !['IDLE', 'BLOCKED'].includes(value.state) : typeof value.run_id !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(value.run_id))) throw new ApiError('Trạng thái Builder không hợp lệ', 502)
  const target = value.target, progress = value.progress
  if (target === null ? value.state !== 'BLOCKED' : !target || Object.keys(target).sort().join() !== ['project_id', 'database', 'namespace'].sort().join() || !Number.isInteger(target.project_id) || target.project_id < 1 || !/^(?:vietroadtraffic|freshsample[a-z0-9]{8,40})$/.test(target.database) || target.namespace !== 'VietRoadTraffic') throw new ApiError('Cấu hình đích Builder không hợp lệ', 502)
  if (progress !== null && (!progress || Object.keys(progress).sort().join() !== ['stage', 'done', 'total'].sort().join() || !['preflight', 'plan', 'vectorize', 'export-artifact', 'write-nodes', 'verify-nodes', 'write-edges', 'verify', 'release'].includes(progress.stage) || !Number.isSafeInteger(progress.done) || !Number.isSafeInteger(progress.total) || progress.done < 0 || progress.total < progress.done)) throw new ApiError('Tiến độ Builder không hợp lệ', 502)
  if (value.error_code !== null && (typeof value.error_code !== 'string' || !/^[A-Z_]{1,32}$/.test(value.error_code))) throw new ApiError('Lỗi Builder không hợp lệ', 502)
  return value
}
export async function loadBuilderStatus(signal?: AbortSignal): Promise<BuilderStatus> {
  return validateBuilder(await api<BuilderStatus>('/admin/kag/builder/status', { signal }))
}
export const builderInputLabels = {
  c3_manifest: 'Manifest nguồn graph',
  sample_manifest: 'Manifest SAMPLE',
  vector_artifact: 'Vector có sẵn',
  provenance: 'Nguồn gốc vector',
  chunk_manifest: 'Manifest phân đoạn',
  source_checkpoint: 'Checkpoint nguồn',
}
export type BuilderInputs = {
  contract_version: 'builder-inputs-v1'
  configuration: 'NOT_CONFIGURED' | 'INVALID' | 'CONFIGURED'
  error_code: 'CONFIG' | null
  scope: 'FRESH_SAMPLE' | null
  target: BuilderStatus['target']
  inputs: { name: keyof typeof builderInputLabels; sha256: string; state: 'MATCHED' | 'MISSING' | 'INVALID' | 'UNAVAILABLE' }[]
  preflight: 'NOT_RUN'
}
export async function loadBuilderInputs(signal?: AbortSignal): Promise<BuilderInputs> {
  const value = await api<BuilderInputs>('/admin/kag/builder/inputs', { signal })
  const invalid = () => { throw new ApiError('Thông tin đầu vào Builder không hợp lệ', 502) }
  if (!shape(value, ['contract_version', 'configuration', 'error_code', 'scope', 'target', 'inputs', 'preflight']) || value.contract_version !== 'builder-inputs-v1' ||
    !['NOT_CONFIGURED', 'INVALID', 'CONFIGURED'].includes(value.configuration) || value.preflight !== 'NOT_RUN' ||
    (value.configuration === 'INVALID' ? value.error_code !== 'CONFIG' : value.error_code !== null)) invalid()
  const configured = value.configuration === 'CONFIGURED', target = value.target
  if (configured ? !shape(target, ['project_id', 'database', 'namespace']) || !Number.isInteger(target!.project_id) || target!.project_id < 1 ||
    !/^(?:neo4j|vietroadtraffic|freshsample[a-z0-9]{8,40})$/.test(target!.database) || target!.namespace !== 'VietRoadTraffic' || value.scope !== 'FRESH_SAMPLE'
    : target !== null || value.scope !== null) invalid()
  if (!Array.isArray(value.inputs) || value.inputs.length !== (configured ? Object.keys(builderInputLabels).length : 0)) invalid()
  const names = new Set<string>()
  for (const input of value.inputs) {
    if (!shape(input, ['name', 'sha256', 'state']) || !Object.prototype.hasOwnProperty.call(builderInputLabels, input.name) || names.has(input.name) ||
      !hash(input.sha256) || !['MATCHED', 'MISSING', 'INVALID', 'UNAVAILABLE'].includes(input.state)) invalid()
    names.add(input.name)
  }
  return value
}
export async function runBuilderAction(action: 'build' | 'stop' | 'resume', run_id: string): Promise<BuilderStatus> {
  if (!['build', 'stop', 'resume'].includes(action) || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(run_id)) throw new ApiError('Yêu cầu Builder không hợp lệ', 422)
  const result = validateBuilder(await api<BuilderStatus>(`/admin/kag/builder/${action}`, send('POST', { run_id })))
  if (result.run_id !== run_id) throw new ApiError('Run Builder không khớp', 502)
  return result
}
export type BenchmarkDatasets = { contract_version: string; state: 'AVAILABLE' | 'NOT_CONFIGURED' | 'UNAVAILABLE' | 'LIMIT_EXCEEDED'; datasets: { id: string; dataset_status: 'FROZEN' | 'PROVISIONAL' | null; dataset_eligibility: 'ELIGIBLE' | 'BLOCKED'; reason: string | null; dataset_hash: string | null; record_count: number | null; official_benchmark: boolean }[]; execution_allowed: false; execution_blockers: string[]; metrics: null }
const states = ['ALIVE', 'READY', 'NOT_READY', 'UNAVAILABLE', 'NOT_CONFIGURED', 'RELEASE_UNAVAILABLE']
export function inspectionError(error: unknown) {
  const status = error instanceof ApiError ? error.status : -1
  return status === 401 ? 'Phiên đã hết hạn. Vui lòng đăng nhập lại.' : status === 403 ? 'Chỉ ADMIN được sử dụng chức năng này.' : status === 422 || status === 400 ? 'Yêu cầu truy xuất không hợp lệ.' : status === 0 ? 'Không kết nối được backend. Hãy thử lại.' : status === 503 ? 'Truy xuất KAG chưa khả dụng hoặc thiếu cấu hình dịch vụ.' : 'Phản hồi KAG chưa đủ bằng chứng hoặc không hợp lệ.'
}
export async function loadKagStatus(signal?: AbortSignal): Promise<KagStatus> {
  const result = await api<KagStatus>('/admin/kag/status', { signal })
  if (!result || Object.keys(result).sort().join() !== ['liveness', 'queryReadiness', 'retrievalReadiness', 'vectorRetrievalReadiness', 'release'].sort().join()) throw new ApiError('Invalid KAG status', 502)
  for (const [key, check] of Object.entries(result)) {
    if (!check || !states.includes(check.state) || !Number.isInteger(check.httpStatus)) throw new ApiError('Invalid KAG status', 502)
    if (check.state === 'ALIVE' && key !== 'liveness') throw new ApiError('Liveness is not readiness', 502)
    if (check.state === 'READY') {
      if (key === 'liveness') throw new ApiError('Liveness is not readiness', 502)
      const evidence = check.evidence
      const verified = key === 'release' ? evidence?.backend_identity_verified === true && evidence?.source_identity_verified === true && evidence?.query_ready === true : key === 'vectorRetrievalReadiness' ? evidence?.status === 'ready' && evidence?.capability === 'retrieve-vector' && evidence?.release_kind === 'SAMPLE' && evidence?.provider_transport === 'not_probed' && evidence?.production_write === 'blocked' : evidence?.status === 'ready' && evidence?.capability === (key === 'queryReadiness' ? 'query-v1' : 'retrieve') && ['auth', 'runtime', 'sources', 'admission'].every(field => (evidence?.checks as Record<string, string>)?.[field] === 'pass')
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
  return validateBenchmark(value)
}
function validateBenchmark(value: BenchmarkDatasets, sample = false): BenchmarkDatasets {
  if (!value || Object.keys(value).sort().join() !== ['contract_version', 'state', 'datasets', 'execution_allowed', 'execution_blockers', 'metrics'].sort().join() || value.contract_version !== 'h1-inspect-v1.0' || value.execution_allowed !== false || value.metrics !== null || !Array.isArray(value.execution_blockers) || value.execution_blockers.join() !== 'OPERATIONAL_PROOF_REQUIRED,BENCHMARK_EXECUTION_NOT_AUTHORIZED' || !['AVAILABLE', 'NOT_CONFIGURED', 'UNAVAILABLE', 'LIMIT_EXCEEDED'].includes(value.state) || !Array.isArray(value.datasets) || value.datasets.length > 20 || (value.state !== 'AVAILABLE' && value.datasets.length)) throw new ApiError('Invalid benchmark proof', 502)
  const seen = new Set<string>()
  for (const row of value.datasets) {
    if (!row || Object.keys(row).sort().join() !== ['id', 'dataset_status', 'dataset_eligibility', 'reason', 'dataset_hash', 'record_count', 'official_benchmark', ...(sample ? ['eligible_count','ineligible_count','invalid_count','gold_count','missing_gold','eligibility_scope', ...('smoke' in row ? ['smoke'] : []), ...('metadata' in row ? ['metadata'] : [])] : [])].sort().join() || typeof row.id !== 'string' || !/^[A-Za-z0-9_.-]{1,128}(?:\/eval_questions\.jsonl)?$/.test(row.id) || row.id.startsWith('../') || seen.has(row.id) || !['ELIGIBLE', 'BLOCKED'].includes(row.dataset_eligibility) || typeof row.official_benchmark !== 'boolean' ||
      (row.dataset_status !== null && !['FROZEN', 'PROVISIONAL'].includes(row.dataset_status)) || (row.dataset_hash !== null && (typeof row.dataset_hash !== 'string' || !/^[0-9a-f]{64}$/.test(row.dataset_hash))) || (row.record_count !== null && (!Number.isInteger(row.record_count) || row.record_count < (sample ? 0 : 1))) || (row.official_benchmark && row.dataset_status !== 'FROZEN') ||
      (row.dataset_eligibility === 'BLOCKED' && !['PROVISIONAL_DATASET', 'NO_GOLD', 'INVALID_DATASET', 'DATASET_TOO_LARGE', ...(sample ? ['NO_ELIGIBLE_QUESTIONS'] : [])].includes(row.reason as string)) ||
      (row.dataset_eligibility === 'ELIGIBLE' && (row.dataset_status !== 'FROZEN' || !row.dataset_hash || !Number.isInteger(row.record_count) || (row.record_count as number) < 1 || row.reason !== null))) throw new ApiError('Invalid dataset proof', 502)
    seen.add(row.id)
  }
  return value
}

export type SampleNode = { entity_type: string; entity_id: string; properties: Record<string, unknown>; sources: { evidence_id: string; field: string; source_sha256: string }[] }
export type SampleEdge = { from: [string, string]; predicate: string; to: [string, string]; properties: Record<string, unknown> }
type BenchmarkConfig = { protocol_version: '1.0'; eval_version: '1.0'; metric_policy_version: '1.0' | '1.1'; ks: number[]; top_k: number; expand: false; rank_semantics: 'channel_projected_returned_top_k'; identity_catalog_hash: string | null; release_id: string | null; judge_config: null | { name: string; version: string; model: string; prompt_version: string; temperature: number; seed: number | null; calibrated: boolean } }
type SmokeRun = { configuration?: BenchmarkConfig; status: 'COMPLETE'; started_at: string; finished_at: string; requested_count: number; attempted_count: number; failed_count: number; ineligible_count: number; metrics: Record<string, { value: number | null; scored_count: number; eligible_count: number; excluded_count: number; failed_count: number; status_counts: Record<'OK' | 'NOT_APPLICABLE' | 'UNAVAILABLE' | 'UNKNOWN', number> }>; latency_ms: Record<'successful' | 'all_attempted', { count: number; min: number | null; mean: number | null; median: number | null; p95: number | null; max: number | null }> }
type Smoke = { state: 'NOT_RUN' | 'AVAILABLE' | 'INVALID_RECEIPT'; review_status: 'PROVISIONAL' | 'FROZEN' | 'NOT_ATTESTED'; g1_eligible_count: number; graph_fingerprint: string; official_benchmark: boolean; runs: Record<'G1' | 'G2', SmokeRun | null> }
type Coverage = BenchmarkDatasets['datasets'][number] & { metadata?: { dataset_version: string | null; category_counts: Record<string, number>; generation_method: string | null }; eligible_count: number; ineligible_count: number; invalid_count: number | null; gold_count: number | null; missing_gold: Record<'document' | 'unit' | 'sign', string[]>; eligibility_scope: 'G1_RETRIEVAL_GOLD_COVERAGE'; smoke?: Smoke }
export type SampleInspection = {
  contract_version: 'h1-sample-inspection-1.0'; release_id: string; release_kind: 'SAMPLE'; source_snapshot_id: string; source_catalog_sha256: string; schema_contract: Record<string, string>; graph_fingerprint: string;
  backend: { database: string; namespace: string; database_id: string; server_id: string; read_only: true; verified: true };
  counts: { nodes: number; edges: number; vectors: number }; nodes: SampleNode[]; edges: SampleEdge[]; verified_at: string; execution_allowed: false; production_write: 'BLOCKED';
  sample_receipt: { stage: 'GRAPH_VERIFIED'; sealed_at: string; receipt_sha256: string; build_run_id: null; progress: null };
  datasets: Omit<BenchmarkDatasets, 'datasets'> & { datasets: Coverage[] };
  providers: { state: 'OBSERVED' | 'NOT_CONFIGURED'; attempts: { embedding: number; chat: number } | null; receipt_window: { since: string; outcomes: Record<string, Record<string, number>>; recent: { kind: string; outcome: string; timestamp: string; attempt: number; request_id: string | null; provider_request_id: string | null; configured_model: string; source_component: string; latency_ms: number | null; status: number | null }[] } | null; configured_chat_model: string | null; configured_embedding_model: string | null; policy_response_version: string | null; exact_backend_identity_verified: false; upstream_attempts: null; proxy_retries: null }
}
const hash = (v: unknown) => typeof v === 'string' && /^[0-9a-f]{64}$/.test(v)
const count = (v: unknown, max = 1000000): v is number => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0 && v <= max
const shape = (v: unknown, keys: string[]) => !!v && typeof v === 'object' && Object.keys(v).sort().join() === keys.sort().join()
function validateSmoke(smoke: Smoke, total: number | null, fingerprint: string) {
  const invalid = () => { throw new ApiError('Invalid smoke proof', 502) }
  if (!shape(smoke,['state','review_status','g1_eligible_count','graph_fingerprint','official_benchmark','runs']) || !['NOT_RUN','AVAILABLE','INVALID_RECEIPT'].includes(smoke.state) || !['PROVISIONAL','FROZEN','NOT_ATTESTED'].includes(smoke.review_status) || !count(smoke.g1_eligible_count,total ?? 0) || smoke.graph_fingerprint !== fingerprint || typeof smoke.official_benchmark !== 'boolean' || !shape(smoke.runs,['G1','G2'])) invalid()
  let hasRun = false
  for (const run of Object.values(smoke.runs)) {
    if (run === null) continue
    hasRun = true
    if (smoke.state !== 'AVAILABLE' || !['PROVISIONAL','FROZEN'].includes(smoke.review_status) || !shape(run,['status','started_at','finished_at','requested_count','attempted_count','failed_count','ineligible_count','metrics','latency_ms', ...('configuration' in run ? ['configuration'] : [])]) || run.status !== 'COMPLETE' || !count(run.requested_count) || run.requested_count < 1 || run.requested_count !== total || !count(run.attempted_count,total) || !count(run.failed_count,run.attempted_count) || !count(run.ineligible_count,total) || run.attempted_count + run.ineligible_count !== total || !Number.isFinite(Date.parse(run.started_at)) || !Number.isFinite(Date.parse(run.finished_at)) || Date.parse(run.finished_at) < Date.parse(run.started_at) || !run.metrics || Array.isArray(run.metrics) || Object.keys(run.metrics).length > 128 || !shape(run.latency_ms,['successful','all_attempted'])) invalid()
    if ('configuration' in run) {
      const c = run.configuration!
      if (!shape(c,['protocol_version','eval_version','metric_policy_version','ks','top_k','expand','rank_semantics','identity_catalog_hash','release_id','judge_config']) || c.protocol_version !== '1.0' || c.eval_version !== '1.0' || !['1.0','1.1'].includes(c.metric_policy_version) || !count(c.top_k,10) || c.top_k < 1 || !Array.isArray(c.ks) || !c.ks.length || c.ks.some((k,i) => !count(k,c.top_k) || k < 1 || i > 0 && k <= c.ks[i-1]) || c.expand !== false || c.rank_semantics !== 'channel_projected_returned_top_k' || c.identity_catalog_hash !== null && !hash(c.identity_catalog_hash) || c.release_id !== null && (typeof c.release_id !== 'string' || !c.release_id)) invalid()
      const j = c.judge_config
      if (j !== null && (!shape(j,['name','version','model','prompt_version','temperature','seed','calibrated']) || typeof j.name !== 'string' || !j.name.trim() || ![j.version,j.model,j.prompt_version].every(v=>typeof v==='string') || typeof j.temperature !== 'number' || !Number.isFinite(j.temperature) || typeof j.calibrated !== 'boolean' || j.seed !== null && !Number.isSafeInteger(j.seed))) invalid()
    }
    for (const metric of Object.values(run.metrics)) {
      if (!shape(metric,['value','scored_count','status_counts','eligible_count','excluded_count','failed_count']) || !shape(metric.status_counts,['OK','NOT_APPLICABLE','UNAVAILABLE','UNKNOWN']) || (metric.value !== null && (!Number.isFinite(metric.value) || metric.value < 0)) || ![metric.scored_count,metric.eligible_count,metric.excluded_count,metric.failed_count,...Object.values(metric.status_counts)].every(v => count(v,total ?? 0)) || Object.values(metric.status_counts).reduce((a,b) => a+b,0) !== total || metric.eligible_count + metric.excluded_count !== total || metric.scored_count !== metric.status_counts.OK || (metric.value === null) !== (metric.scored_count === 0)) invalid()
    }
    for (const latency of Object.values(run.latency_ms)) {
      if (!shape(latency,['count','min','mean','median','p95','max']) || !count(latency.count,total ?? 0) || [latency.min,latency.mean,latency.median,latency.p95,latency.max].some(v => latency.count === 0 ? v !== null : v === null || !Number.isFinite(v) || v < 0)) invalid()
    }
  }
  if ((smoke.state === 'AVAILABLE') !== hasRun) invalid()
}
export async function loadSampleInspection(signal?: AbortSignal): Promise<SampleInspection> {
  const value = await api<SampleInspection>('/admin/kag/sample', { signal })
  const invalid = () => { throw new ApiError('Unverified sample inspection', 502) }
  if (!shape(value, ['contract_version','release_id','release_kind','source_snapshot_id','source_catalog_sha256','schema_contract','graph_fingerprint','backend','counts','nodes','edges','verified_at','execution_allowed','production_write','sample_receipt','datasets','providers']) || value.contract_version !== 'h1-sample-inspection-1.0' || value.release_kind !== 'SAMPLE' || !value.release_id || !value.source_snapshot_id || !hash(value.graph_fingerprint) || !hash(value.source_catalog_sha256) || value.execution_allowed !== false || value.production_write !== 'BLOCKED' || !Number.isFinite(Date.parse(value.verified_at))) invalid()
  if (!shape(value.backend,['database','namespace','database_id','server_id','read_only','verified']) || value.backend.read_only !== true || value.backend.verified !== true || value.backend.database !== 'vietroadtraffic' || value.backend.namespace !== 'VietRoadTraffic' || !value.backend.database_id || !value.backend.server_id || !shape(value.schema_contract,['namespace','schema_sha256','contract_sha256']) || value.schema_contract.namespace !== 'VietRoadTraffic' || !hash(value.schema_contract.schema_sha256) || !hash(value.schema_contract.contract_sha256)) invalid()
  if (!shape(value.counts,['nodes','edges','vectors']) || !count(value.counts.nodes,32) || !value.counts.nodes || !count(value.counts.edges,22) || !count(value.counts.vectors,42) || !value.counts.vectors || !Array.isArray(value.nodes) || value.nodes.length !== value.counts.nodes || !Array.isArray(value.edges) || value.edges.length !== value.counts.edges) invalid()
  const nodes = new Set<string>(), sources = new Set<string>()
  for (const n of value.nodes) {
    if (!shape(n,['entity_type','entity_id','properties','sources']) || !['VietRoadTraffic.LegalDocument','VietRoadTraffic.LegalUnit','VietRoadTraffic.TrafficSign'].includes(n.entity_type) || typeof n.entity_id !== 'string' || !n.entity_id || !n.properties || n.properties.id !== n.entity_id || n.properties.name !== n.entity_id || nodes.has(JSON.stringify([n.entity_type,n.entity_id])) || !Array.isArray(n.sources) || !n.sources.length || n.sources.length > 2 || Object.keys(n.properties).some(k => k.endsWith('_vector') || ['password','credential','token'].includes(k))) invalid()
    nodes.add(JSON.stringify([n.entity_type,n.entity_id]))
    for (const s of n.sources) {
      if (!shape(s,['evidence_id','field','source_sha256']) || !hash(s.evidence_id) || !hash(s.source_sha256) || typeof s.field !== 'string' || !(s.field in n.properties) || sources.has(s.evidence_id)) invalid()
      sources.add(s.evidence_id)
    }
  }
  for (const e of value.edges) if (!shape(e,['from','predicate','to','properties']) || !Array.isArray(e.from) || e.from.length !== 2 || !Array.isArray(e.to) || e.to.length !== 2 || !nodes.has(JSON.stringify(e.from)) || !nodes.has(JSON.stringify(e.to)) || typeof e.predicate !== 'string' || !e.predicate || !e.properties || typeof e.properties !== 'object') invalid()
  if (!shape(value.sample_receipt,['stage','sealed_at','receipt_sha256','build_run_id','progress']) || value.sample_receipt.stage !== 'GRAPH_VERIFIED' || !hash(value.sample_receipt.receipt_sha256) || !Number.isFinite(Date.parse(value.sample_receipt.sealed_at)) || value.sample_receipt.build_run_id !== null || value.sample_receipt.progress !== null) invalid()
  validateBenchmark(value.datasets,true)
  for (const row of value.datasets.datasets) {
    if ('metadata' in row) {
      const m = row.metadata!, categories = ['definition','obligation','sanction_numeric','effectiveness_metadata','inter_document','multi_hop','unanswerable','traffic_sign']
      if (!shape(m,['dataset_version','category_counts','generation_method']) || m.dataset_version !== null && (typeof m.dataset_version !== 'string' || !m.dataset_version.trim() || m.dataset_version.length > 512) || !m.category_counts || Array.isArray(m.category_counts) || typeof m.category_counts !== 'object' || Object.entries(m.category_counts).some(([cat,n]) => !categories.includes(cat) || !count(n) || n < 1) || m.generation_method !== null && m.generation_method !== 'legacy-b2-evidence-first-adapted') invalid()
      const total = Object.values(m.category_counts).reduce((a,b) => a+b,0)
      if (row.record_count !== null && (total !== row.record_count - (row.invalid_count ?? 0) || (m.dataset_version === null) !== (total === 0))) invalid()
    }
    if (row.smoke) {
      validateSmoke(row.smoke,row.record_count,value.graph_fingerprint)
      if (row.smoke.official_benchmark !== row.official_benchmark || row.smoke.review_status !== 'NOT_ATTESTED' && row.smoke.review_status !== row.dataset_status) invalid()
      for (const run of Object.values(row.smoke.runs)) if (run?.configuration?.release_id !== undefined && run.configuration.release_id !== null && run.configuration.release_id !== value.release_id) invalid()
    }
    if (row.eligibility_scope !== 'G1_RETRIEVAL_GOLD_COVERAGE' || !count(row.eligible_count) || !count(row.ineligible_count) || !shape(row.missing_gold,['document','unit','sign']) || Object.values(row.missing_gold).some(ids => !Array.isArray(ids) || ids.some(id => typeof id !== 'string' || !id)) || (row.record_count !== null && (!count(row.invalid_count) || !count(row.gold_count,row.record_count) || row.eligible_count + row.ineligible_count + (row.invalid_count as number) !== row.record_count))) invalid()
  }
  const p = value.providers
  if (!shape(p,['state','attempts','receipt_window','configured_chat_model','configured_embedding_model','policy_response_version','exact_backend_identity_verified','upstream_attempts','proxy_retries']) || !['OBSERVED','NOT_CONFIGURED'].includes(p.state) || p.exact_backend_identity_verified !== false || p.upstream_attempts !== null || p.proxy_retries !== null) invalid()
  if (p.state === 'NOT_CONFIGURED') { if (p.attempts !== null || p.receipt_window !== null) invalid() }
  else if (!p.attempts || !shape(p.attempts,['embedding','chat']) || !Object.values(p.attempts).every(v => count(v,Number.MAX_SAFE_INTEGER)) || p.configured_chat_model !== 'gemini-3.8-flash-high' || p.configured_embedding_model !== 'dg/text-embedding-3-large' || !p.receipt_window || !shape(p.receipt_window,['since','outcomes','recent']) || !Array.isArray(p.receipt_window.recent) || p.receipt_window.recent.length > 50) invalid()
  return value
}
