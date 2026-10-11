import { useEffect, useState } from 'react'
import { Page, Button } from '../../admin/ui'
import { Notice } from './shared'
import { loadKagStatus, loadPipelineStatus, loadBenchmarkDatasets, inspectionError } from './kag-inspection'

function useInspection<T>(load: (signal?: AbortSignal) => Promise<T>) {
  const [value, setValue] = useState<T>(), [error, setError] = useState(''), [loading, setLoading] = useState(true), [version, setVersion] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(''); setValue(undefined)
    load(controller.signal).then(result => { if (!controller.signal.aborted) setValue(result) }).catch(failure => { if (!controller.signal.aborted) setError(inspectionError(failure)) }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [load, version])
  return { value, error, loading, reload: () => setVersion(v => v + 1) }
}

export function Graph() {
  const data = useInspection(loadKagStatus), release = data.value?.release
  return <Page title="Đồ thị tri thức" subtitle="Thông tin serving release từ KAG; artifact không chứng minh physical database hoặc graph live sẵn sàng." actions={<Button disabled={data.loading} onClick={data.reload}>Kiểm tra lại</Button>}>
    <Notice {...data} retry={data.reload} />
    {data.value && <>
      <p className="py-4">Query: {data.value.queryReadiness.state} · Retrieval: {data.value.retrievalReadiness.state}</p>
      <p>Release: {release?.state}{release?.code ? ` · ${release.code}` : ''}</p>
      {release?.evidence && <pre className="mt-4 text-xs whitespace-pre-wrap break-words">{JSON.stringify(release.evidence, null, 2)}</pre>}
      <p className="mt-4 text-sm text-muted">Chưa có endpoint đọc graph live đã được cấp quyền. Không hiển thị số node, cạnh hoặc sơ đồ từ dữ liệu chưa xác minh.</p>
    </>}
  </Page>
}

export function Pipeline() {
  const data = useInspection(loadPipelineStatus)
  return <Page title="Pipeline KAG" subtitle="Trạng thái slot xử lý của API tại lần kiểm tra; không phải tiến độ build graph." actions={<Button disabled={data.loading} onClick={data.reload}>Kiểm tra lại</Button>}>
    <Notice {...data} retry={data.reload} />
    {data.value && <>
      <p className="py-4">Runtime: {data.value.phase} · Request đang xử lý: {data.value.active_requests ?? 'Chưa xác minh'}</p>
      <p>Tiến độ các stage: chưa có telemetry được xác minh.</p>
      <pre className="mt-4 text-xs whitespace-pre-wrap break-words">{JSON.stringify(data.value, null, 2)}</pre>
    </>}
    <p className="mt-5 text-sm text-muted">Không được chạy pipeline, restore hoặc ghi graph trong phạm vi hiện tại.</p>
  </Page>
}

export function Benchmark() {
  const data = useInspection(loadBenchmarkDatasets)
  return <Page title="Benchmark KAG" subtitle="Catalog read-only sử dụng evaluation framework hiện có; không chạy benchmark." actions={<Button disabled={data.loading} onClick={data.reload}>Kiểm tra lại</Button>}>
    <Notice {...data} retry={data.reload} empty={data.value?.state === 'AVAILABLE' && !data.value.datasets.length} />
    {data.value && <>
      <p className="py-4">Catalog: {data.value.state} · Quyền thực thi: BLOCKED</p>
      {data.value.datasets.map(row => <section key={row.id} className="py-4 border-b border-line">
        <h2 className="font-semibold break-words">{row.id}</h2>
        <p className="text-sm mt-2">{row.dataset_status ?? 'Không hợp lệ'} · Dataset {row.dataset_eligibility}{row.reason ? ` · ${row.reason}` : ''}</p>
        <p className="text-sm mt-2">Số câu: {row.record_count ?? 'Chưa xác minh'} · Official benchmark: {row.official_benchmark ? 'Có trong manifest' : 'Không'}</p>
        {row.dataset_hash && <p className="text-xs mt-2 break-all">SHA-256: {row.dataset_hash}</p>}
      </section>)}
      <p className="mt-5 text-sm text-muted">FROZEN và ELIGIBLE chỉ chứng minh dataset integrity/khả năng đánh giá. Chưa xác minh runtime, gold với graph hiện tại hoặc quyền chạy benchmark; chưa có metrics.</p>
    </>}
  </Page>
}
