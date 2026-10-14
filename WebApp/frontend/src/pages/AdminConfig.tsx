import { Notice,useData } from './server/shared'
import { type SchemaResponse } from './server/KagSchemaPage'
import { useMemo, useState } from 'react'
import { defaultConfig, useAdmin, type KagConfig } from '../admin/store'
import { Button, Card, Field, Page, Terminal, inputCls } from '../admin/ui'

function toYaml(c: KagConfig) {
  return [
    'project:',
    `  biz_scene: ${c.bizScene}`,
    `  language: ${c.language}`,
    `  host_addr: ${c.hostAddr}`,
    '',
    ...(['openie_llm', 'chat_llm'] as const).map((k) => `${k}:\n  type: openai\n  base_url: ${c.baseUrl}\n  api_key: ${c.apiKey ? '********' : '<chưa đặt>'}\n  model: ${k === 'openie_llm' ? c.openieModel : c.chatModel}\n`),
    'vectorize_model:',
    '  type: openai',
    `  base_url: ${c.baseUrl}`,
    `  model: ${c.vectorModel}`,
    '',
    'kag_builder_pipeline:',
    `  num_chains: ${c.chainNum}`,
    `  num_threads_per_chain: ${c.threadNum}`,
    '  splitter:',
    `    split_length: ${c.splitLength}`,
    `    window_length: ${c.splitOverlap}`,
    ...(c.similarityThreshold != null ? [`  similarity_threshold: ${c.similarityThreshold}`] : ['  # similarity_threshold: (tắt fuzzy linking)']),
    '',
    'kag_solver_pipeline:',
    `  pipeline: ${c.solverVariant === 'baseline' ? 'kag_static_pipeline' : 'evidence_aware_iterative_pipeline'}`,
    '  planner: lf_kag_static_planner',
    '  executors: [hybrid-retrieval, py-math, deduce, output]',
    '  retrievers:',
    `    kg_cs: { threshold: ${c.kgCsThreshold} }`,
    `    kg_fr: { top_k: ${c.kgFrTopK}, threshold: ${c.kgFrThreshold} }`,
    `    rc:    { top_k: ${c.rcTopK}, score_threshold: ${c.rcScoreThreshold} }`,
    '  generator: llm_index_generator',
    `  enable_ref: ${c.enableRef}`,
    'eval:',
    `  thread_num: ${c.evalThreads}`,
    `  upper_limit: ${c.evalUpperLimit}`,
  ].join('\n')
}

export default function AdminConfig() {
  const schema=useData<SchemaResponse>('/admin/kag/schema')
  const { config, setConfig, notify, runTask } = useAdmin()
  const [draft, setDraft] = useState(config)
  const [showKey, setShowKey] = useState(false)
  const [testing, setTesting] = useState<null | 'ok' | 'run'>(null)
  const dirty = JSON.stringify(draft) !== JSON.stringify(config)
  const yaml = useMemo(() => toYaml(draft), [draft])
  const set = <K extends keyof KagConfig>(k: K, v: KagConfig[K]) => setDraft((d) => ({ ...d, [k]: v }))
  const num = (k: keyof KagConfig) => (e: React.ChangeEvent<HTMLInputElement>) => set(k, Number(e.target.value) as never)

  return (
    <Page
      title="Cấu hình"
      subtitle="Form cấu hình và kiểm tra mô hình: Demo, không sửa runtime. Schema/contract hiện tại đọc từ API thật."
      actions={
        <>
          <Button variant="ghost" onClick={() => setDraft(defaultConfig)}>Khôi phục mặc định</Button>
          <Button variant="ghost" disabled={!dirty} onClick={() => setDraft(config)}>Huỷ thay đổi</Button>
          <Button variant="primary" disabled={!dirty} onClick={() => { setConfig(draft); notify('Demo: đã lưu cấu hình trong phiên trình duyệt; không ghi kag_config.yaml') }}>Lưu cấu hình · Demo</Button>
        </>
      }
    >
      <Notice {...schema} retry={schema.reload}/><Card title="Schema & contract · API thật" className="mb-5"><div className="px-5 pb-5 text-xs">{schema.value?<><p className="break-all">Namespace: {schema.value.identity.namespace} · SHA-256: {schema.value.identity.schema_sha256}</p><details className="mt-3"><summary>Node, quan hệ và runtime contract chỉ đọc</summary><pre className="whitespace-pre-wrap break-all mt-3">{JSON.stringify(schema.value.contract,null,2)}</pre></details><a className="underline inline-block mt-3" href="/admin/schema">Xem bảng schema và tải contract</a></>:<p>Chưa đọc được schema</p>}</div></Card><p className="mb-4 text-xs text-muted">Các form và YAML bên dưới dùng dữ liệu Demo. Không phải cấu hình live, không thay đổi secrets hoặc runtime.</p>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="space-y-5">
          <Card title="Dự án">
            <div className="grid gap-4 px-5 pb-5 sm:grid-cols-3">
              <Field label="biz_scene" hint={draft.bizScene === 'default' ? '⚠ "default" sẽ chuyển prompt sang tiếng Anh' : 'Dùng prompt tiếng Việt legal_ner / legal_triple'}>
                <select className={inputCls} value={draft.bizScene} onChange={(e) => set('bizScene', e.target.value as KagConfig['bizScene'])}>
                  <option value="legal">legal</option>
                  <option value="default">default</option>
                </select>
              </Field>
              <Field label="Ngôn ngữ">
                <select className={inputCls} value={draft.language} onChange={(e) => set('language', e.target.value as KagConfig['language'])}>
                  <option value="vi">Tiếng Việt</option>
                  <option value="en">English</option>
                </select>
              </Field>
              <Field label="OpenSPG host"><input className={inputCls} value={draft.hostAddr} onChange={(e) => set('hostAddr', e.target.value)} /></Field>
            </div>
          </Card>

          <Card
            title="Mô hình (OpenAI-compatible)"
            right={
              <Button size="sm" onClick={() => { setTesting('run'); window.setTimeout(() => { setTesting('ok'); notify('Demo: mô phỏng kết nối thành công; không gọi provider') }, 1100) }}>
                {testing === 'run' ? 'Đang kiểm tra…' : testing === 'ok' ? '✓ Demo kết nối OK' : 'Kiểm tra kết nối · Demo'}
              </Button>
            }
          >
            <div className="grid gap-4 px-5 pb-5 sm:grid-cols-2">
              <Field label="Base URL" hint="Phải kết thúc bằng /v1">
                <input className={inputCls} value={draft.baseUrl} onChange={(e) => set('baseUrl', e.target.value)} />
              </Field>
              <Field label="API key" hint="Demo trong phiên trình duyệt; không lưu secrets server">
                <div className="flex gap-2">
                  <input type={showKey ? 'text' : 'password'} className={inputCls} value={draft.apiKey} onChange={(e) => set('apiKey', e.target.value)} placeholder="sk-…" />
                  <Button size="sm" variant="ghost" onClick={() => setShowKey((v) => !v)}>{showKey ? 'Ẩn' : 'Hiện'}</Button>
                </div>
              </Field>
              <Field label="openie_llm"><input className={inputCls} value={draft.openieModel} onChange={(e) => set('openieModel', e.target.value)} /></Field>
              <Field label="chat_llm"><input className={inputCls} value={draft.chatModel} onChange={(e) => set('chatModel', e.target.value)} /></Field>
              <Field label="vectorize_model"><input className={inputCls} value={draft.vectorModel} onChange={(e) => set('vectorModel', e.target.value)} /></Field>
            </div>
          </Card>

          <Card title="Builder & solver">
            <div className="grid gap-4 px-5 pb-5 sm:grid-cols-3">
              <Field label="Số chain"><input type="number" min={1} max={16} className={inputCls} value={draft.chainNum} onChange={num('chainNum')} /></Field>
              <Field label="Thread / chain"><input type="number" min={1} max={16} className={inputCls} value={draft.threadNum} onChange={num('threadNum')} /></Field>
              <Field label="top_k truy xuất"><input type="number" min={1} max={100} className={inputCls} value={draft.topK} onChange={num('topK')} /></Field>
              <Field label="split_length"><input type="number" className={inputCls} value={draft.splitLength} onChange={num('splitLength')} /></Field>
              <Field label="window_length"><input type="number" className={inputCls} value={draft.splitOverlap} onChange={num('splitOverlap')} /></Field>
              <Field label="similarity_threshold" hint="Để trống = tắt fuzzy linking">
                <input type="number" step="0.05" min={0} max={1} className={inputCls} value={draft.similarityThreshold ?? ''} onChange={(e) => set('similarityThreshold', e.target.value === '' ? null : Number(e.target.value))} />
              </Field>
              <Field label="eval thread_num"><input type="number" min={1} className={inputCls} value={draft.evalThreads} onChange={num('evalThreads')} /></Field>
              <Field label="eval upper_limit"><input type="number" min={1} className={inputCls} value={draft.evalUpperLimit} onChange={num('evalUpperLimit')} /></Field>
            </div>
          </Card>
          <Card title="Solver & retriever" right={<span className="text-[11.5px] text-muted">kag_static_pipeline</span>}>
            <div className="grid gap-4 px-5 pb-5 sm:grid-cols-3">
              <Field label="Biến thể solver" hint={draft.solverVariant === 'evidence_aware' ? 'solver_improvement: verifier + updater lặp theo bằng chứng' : 'kag/solver baseline'}>
                <select className={inputCls} value={draft.solverVariant} onChange={(e) => set('solverVariant', e.target.value as KagConfig['solverVariant'])}>
                  <option value="baseline">baseline</option>
                  <option value="evidence_aware">evidence-aware iterative</option>
                </select>
              </Field>
              <Field label="kg_cs threshold"><input type="number" step="0.05" min={0} max={1} className={inputCls} value={draft.kgCsThreshold} onChange={num('kgCsThreshold')} /></Field>
              <Field label="enable_ref">
                <select className={inputCls} value={String(draft.enableRef)} onChange={(e) => set('enableRef', e.target.value === 'true')}>
                  <option value="true">true — kèm trích dẫn</option>
                  <option value="false">false</option>
                </select>
              </Field>
              <Field label="kg_fr top_k"><input type="number" min={1} className={inputCls} value={draft.kgFrTopK} onChange={num('kgFrTopK')} /></Field>
              <Field label="kg_fr threshold"><input type="number" step="0.05" min={0} max={1} className={inputCls} value={draft.kgFrThreshold} onChange={num('kgFrThreshold')} /></Field>
              <div />
              <Field label="rc top_k" hint="Tăng nếu Điều đúng không lọt top-k (lỗi C4)"><input type="number" min={1} className={inputCls} value={draft.rcTopK} onChange={num('rcTopK')} /></Field>
              <Field label="rc score_threshold" hint="Hạ để nới recall chunk"><input type="number" step="0.05" min={0} max={1} className={inputCls} value={draft.rcScoreThreshold} onChange={num('rcScoreThreshold')} /></Field>
            </div>
          </Card>
        </div>

        <div className="space-y-4 xl:sticky xl:top-6 self-start">
          <Card title="Xem trước kag_config.yaml" right={dirty && <span className="text-[11.5px] font-medium text-accent-strong">Chưa lưu</span>}>
            <div className="px-5 pb-5">
              <Terminal lines={yaml.split('\n')} className="max-h-[520px]" />
              <div className="mt-3 flex gap-2">
                <Button size="sm" onClick={() => { navigator.clipboard?.writeText(yaml); notify('Đã sao chép YAML') }}>Sao chép</Button>
                <Button size="sm" onClick={() => runTask('schema-commit')}>Áp dụng & commit schema</Button>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </Page>
  )
}
