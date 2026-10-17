import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { BuilderControls, useInspection } from './server/KagManagement'
import { builderInputLabels, inspectionError, loadBuilderInputs, loadKagStatus, loadSampleInspection, loadBenchmarkDatasets } from './server/kag-inspection'
import { Notice } from './server/shared'
import type { JobStatus } from '../admin/store'
import { Button, Card, Page, type Tone } from '../admin/ui'

export const jobTone: Record<JobStatus, [Tone, string]> = {
  queued: ['gray', 'Chờ'],
  running: ['gold', 'Đang chạy'],
  success: ['green', 'Thành công'],
  failed: ['red', 'Lỗi'],
  cancelled: ['gray', 'Đã huỷ'],
}

export default function AdminPipeline() {
  const data = useInspection(loadBuilderInputs), inputs = data.value
  const connection = useInspection(loadKagStatus)
  const graph = useInspection(loadSampleInspection), sample = graph.value
  const evaluation = useInspection(loadBenchmarkDatasets)
  const [checking, setChecking] = useState(false), [checkError, setCheckError] = useState('')
  const source = inputs?.source_validation
  useEffect(() => {
    if (source?.state !== 'CHECKING' || data.loading) return
    const timer = setTimeout(data.reload, 1500)
    return () => clearTimeout(timer)
  }, [source, data.loading, data.reload])
  async function checkSource() {
    setChecking(true); setCheckError('')
    try { data.setValue(await loadBuilderInputs(undefined, true)) }
    catch (failure) { data.setValue(undefined); setCheckError(inspectionError(failure)) }
    finally { setChecking(false) }
  }
  const inputStates = { NOT_CHECKED: 'Chưa kiểm checksum', MATCHED: 'Khớp checksum cấu hình', MISSING: 'Thiếu file', INVALID: 'Sai checksum', UNAVAILABLE: 'Không đọc được' }
  const configuration = inputs ? inputs.configuration === 'NOT_CONFIGURED' ? 'Chưa cấu hình' : inputs.configuration === 'INVALID' ? 'Cấu hình không hợp lệ' : `Đã đọc cấu hình ${inputs.scope === 'PRODUCTION' ? 'full corpus' : 'SAMPLE'}` : data.loading ? 'Đang kiểm tra' : 'Chưa đọc được'
  const sourceStates = { NOT_RUN: 'Chưa kiểm nguồn', CHECKING: 'Đang kiểm nguồn', VALID: 'Nguồn hợp lệ', INVALID: 'Nguồn không hợp lệ', UNAVAILABLE: 'Không kiểm được nguồn' }
  const checks = { liveness: 'Kết nối API', queryReadiness: 'Truy vấn', retrievalReadiness: 'Retrieval', vectorRetrievalReadiness: 'Vector retrieval', release: 'Release' } as const
  return (
    <Page
      title="Pipeline & tác vụ"
      subtitle="Chuẩn bị nguồn, theo dõi Builder và kiểm chứng kết quả KAG."
    >
      <section aria-label="Tổng quan" className="mb-5 border-b border-line pb-4 text-sm">
        <h2 className="font-semibold mb-2">Tổng quan</h2>
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          <p>Đầu vào: {configuration}</p>
          <p>KAG API: {connection.value?.liveness.state ?? (connection.loading ? 'Đang kiểm tra' : 'Chưa đọc được')}</p>
          <p>Graph SAMPLE: {sample ? 'Có dữ liệu xác minh' : graph.loading ? 'Đang kiểm tra' : 'Chưa xác minh'}</p>
        </div>
        <p className="mt-2 text-muted">Kiểm nguồn độc lập với đích Build và quyền ghi. Trạng thái Worker hiển thị bên dưới.</p>
      </section>
      <div className="grid gap-5 xl:grid-cols-2 items-start">
      <Card title="Nguồn & chuẩn bị dữ liệu">
        <div className="px-5 pb-5 text-sm space-y-3">
          <p>Nhập danh mục, bổ sung metadata và tệp nguồn; kiểm duyệt trước khi xuất bản trên WebApp.</p>
          <nav aria-label="Quản lý nguồn" className="flex flex-wrap gap-3">
            <Link className="underline" to="/admin/imports?type=documents">Nhập danh mục</Link>
            <Link className="underline" to="/admin/knowledge">Quản lý nguồn & kiểm duyệt</Link>
          </nav>
          <p className="text-muted">Dữ liệu WebApp chưa tự động chuyển thành đầu vào KAG Builder.</p>
        </div>
      </Card>
      <Card title="Đầu vào & điều kiện Build">
        <div className="px-5 pb-5 text-sm space-y-3 min-w-0">
          <Notice {...data} />
          {checkError && <p role="alert">{checkError}</p>}
          {inputs && <>
            <p>Cấu hình: {configuration}</p>
            {inputs.error_code && <p>Mã lỗi cấu hình: {inputs.error_code}</p>}
            {inputs.target ? <p className="break-words">Đích cấu hình: project {inputs.target.project_id} · database {inputs.target.database} · {inputs.target.namespace} · {inputs.scope}</p> : <p>Đích Build: Chưa cấu hình</p>}
            {!inputs.inputs.length && <p>Nguồn / manifest: Chưa cấu hình</p>}
            <p aria-live="polite">Kiểm nguồn: {sourceStates[inputs.source_validation.state]}{source?.error_code ? ` · ${source.error_code}` : ''}</p>
            {source?.state === 'VALID' && <><p>{source.nodes} node · {source.edges} cạnh trong kế hoạch nguồn</p><details><summary className="cursor-pointer underline">SHA-256 kế hoạch đã kiểm</summary><p className="break-all mt-1">{source.plan_sha256}</p></details></>}
            {!!inputs.inputs.length && <>
              <dl className="grid grid-cols-2 gap-3">
                {Object.entries(inputStates).map(([state, label]) => <div key={state}><dt className="text-muted">{label}</dt><dd className="font-semibold">{inputs.inputs.filter(input => input.state === state).length}{state === 'MATCHED' ? ` / ${inputs.inputs.length} file` : ' file'}</dd></div>)}
              </dl>
              {inputs.inputs.some(input => ['MISSING', 'INVALID', 'UNAVAILABLE'].includes(input.state)) && <p>Cần xử lý file thiếu, sai checksum hoặc không đọc được.</p>}
              <details><summary className="cursor-pointer underline">Chi tiết đầu vào</summary>
            {inputs.inputs.map(input => <div key={input.name} className="border-b border-line py-2">
              <p>{builderInputLabels[input.name]}: {inputStates[input.state]}</p>
              <details className="mt-1"><summary className="cursor-pointer underline">SHA-256 theo cấu hình</summary><p className="break-all mt-1">{input.sha256}</p></details>
            </div>)}
              </details>
            </>}
          </>}
          <p>Preflight đích: chưa chạy. Vector và quyền ghi chưa được xác minh bởi kiểm nguồn.</p>
          <details className="text-muted"><summary className="cursor-pointer underline">Phạm vi kiểm tra</summary><p className="mt-2">Kiểm nguồn xác thực manifest, checksum, schema, ID và quan hệ trong kế hoạch. Kết quả mất hiệu lực khi đầu vào đổi. Identity đích, vector và GraphLock được Runner kiểm riêng; nguồn hợp lệ không tự bật Build.</p></details>
          <div className="flex flex-wrap gap-3"><Button disabled={checking || source?.state === 'CHECKING' || inputs?.configuration !== 'CONFIGURED'} onClick={checkSource}>Kiểm tra nguồn</Button><Button disabled={data.loading || checking} onClick={data.reload}>Tải lại đầu vào</Button></div>
        </div>
      </Card>
      <div className="lg:col-span-2 min-w-0"><BuilderControls /></div>
      <Card title="Kiểm chứng graph">
        <div className="px-5 pb-5 text-sm space-y-3">
          <Notice {...graph} />
          {sample && <>
            <p>{sample.counts.nodes} node · {sample.counts.edges} cạnh · {sample.counts.vectors} vector</p>
            <p className="break-all">Release: {sample.release_id}</p>
            <p>Xác minh lúc: {sample.verified_at}</p>
            <details><summary className="cursor-pointer underline">Đích graph & receipt</summary><div className="mt-2 space-y-2 break-all"><p>{sample.backend.database} · {sample.backend.namespace}</p><p>Fingerprint: {sample.graph_fingerprint}</p><p>{sample.sample_receipt.stage} · {sample.sample_receipt.sealed_at}</p></div></details>
          </>}
          <p className="text-muted">Kết quả kiểm tra graph SAMPLE độc lập với phiên Builder hiện tại.</p>
          <div className="flex flex-wrap items-center gap-3"><Button disabled={graph.loading} onClick={graph.reload}>Kiểm tra graph</Button><Link className="underline" to="/admin/graph">Mở Graph</Link></div>
        </div>
      </Card>
      <Card title="Kết nối & Retrieval">
        <div className="px-5 pb-5 text-sm space-y-3">
          <Notice {...connection} />
          {connection.value && <dl className="space-y-2">{Object.entries(checks).map(([key, label]) => {
            const check = connection.value![key as keyof typeof checks]
            return <div key={key} className="flex flex-wrap justify-between gap-2"><dt>{label}</dt><dd className="break-all">{check.state}{check.code ? ` · ${check.code}` : ''}</dd></div>
          })}</dl>}
          <p className="text-muted">Kết nối API không chứng minh truy xuất sẵn sàng. Chỉ gọi embedding khi bạn chạy thử Retrieval tại Hạ tầng.</p>
          <div className="flex flex-wrap items-center gap-3"><Button disabled={connection.loading} onClick={connection.reload}>Kiểm tra kết nối</Button><Link className="underline" to="/admin/infrastructure">Mở Hạ tầng & Retrieval</Link></div>
        </div>
      </Card>
      <Card title="Đánh giá" className="lg:col-span-2">
        <div className="px-5 pb-5 text-sm space-y-3">
          <Notice {...evaluation} />
          {evaluation.value && <>
            <p>Catalog: {evaluation.value.state} · {evaluation.value.datasets.length} bộ dữ liệu</p>
            {!!evaluation.value.datasets.length && <details><summary className="cursor-pointer underline">Chi tiết bộ dữ liệu</summary><ul className="mt-2 space-y-2">{evaluation.value.datasets.map(row => <li key={row.id} className="break-words">{row.id} · {row.record_count ?? 'Chưa đo'} bản ghi · {row.dataset_status ?? 'Chưa xác minh'} · {row.dataset_eligibility}{row.reason ? ` · ${row.reason}` : ''}</li>)}</ul></details>}
          </>}
          <p className="text-muted">Chưa hỗ trợ chạy benchmark tại đây. Xem artifact KAG thực đo tại Benchmark; catalog không chứng minh chất lượng trả lời.</p>
          <div className="flex flex-wrap items-center gap-3"><Button disabled={evaluation.loading} onClick={evaluation.reload}>Kiểm tra dataset</Button><Link className="underline" to="/admin/benchmark">Xem Benchmark</Link></div>
        </div>
      </Card>
      </div>
    </Page>
  )
}
