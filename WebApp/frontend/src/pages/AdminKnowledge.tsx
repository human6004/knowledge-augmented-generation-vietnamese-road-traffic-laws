import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAdmin, type DocStatus, type LegalDoc } from '../admin/store'
import { Badge, Button, Card, Field, Modal, Page, Progress, Td, Th, inputCls, type Tone } from '../admin/ui'

const pipelineSteps = ['Tách Điều / Khoản / Điểm', 'Trích xuất thực thể & quan hệ', 'Dựng đồ thị & vector', 'Kiểm duyệt bởi quản trị viên', 'Xuất bản phiên bản mới']

const statusTone: Record<DocStatus, Tone> = {
  'Chờ xử lý': 'gray',
  'Đang xử lý': 'gold',
  'Chờ duyệt': 'amber',
  'Đã lập chỉ mục': 'green',
  'Lưu trữ': 'gray',
  'Lỗi': 'red',
}

export default function AdminKnowledge() {
  const nav = useNavigate()
  const { docs, setDocs, notify, config } = useAdmin()
  const [dragOver, setDragOver] = useState(false)
  const [selectedId, setSelectedId] = useState(docs[2]?.id ?? docs[0]?.id)
  const [filter, setFilter] = useState<'all' | DocStatus>('all')
  const [urlOpen, setUrlOpen] = useState(false)
  const [url, setUrl] = useState('')
  const [query, setQuery] = useState('')
  const [result, setResult] = useState<null | { lf: string[]; nodes: string[]; answer: string }>(null)
  const [querying, setQuerying] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const selected = docs.find((d) => d.id === selectedId)
  const shown = filter === 'all' ? docs : docs.filter((d) => d.status === filter)

  const update = (id: string, patch: Partial<LegalDoc>) => setDocs((ds) => ds.map((d) => (d.id === id ? { ...d, ...patch } : d)))

  function processDoc(id: string, from = 0) {
    update(id, { status: 'Đang xử lý', step: from })
    let s = from
    const t = window.setInterval(() => {
      s++
      setDocs((ds) =>
        ds.map((d) =>
          d.id === id
            ? { ...d, step: s, chunks: d.chunks + Math.round(40 + Math.random() * 60), entities: d.entities + Math.round(200 + Math.random() * 300), status: s >= 3 ? 'Chờ duyệt' : 'Đang xử lý' }
            : d
        )
      )
      if (s >= 3) {
        window.clearInterval(t)
        notify('Đã dựng đồ thị — chờ kiểm duyệt')
      }
    }, 900)
  }

  function addDocs(names: string[]) {
    const created: LegalDoc[] = names.map((n, i) => ({
      id: 'd' + Date.now() + i,
      name: n.replace(/\.(pdf|docx?|md)$/i, ''),
      type: /luật/i.test(n) ? 'Luật' : /thông tư|tt/i.test(n) ? 'Thông tư' : 'Nghị định',
      effective: '[từ ngày]',
      status: 'Chờ xử lý',
      chunks: 0,
      entities: 0,
      step: 0,
      updated: new Date().toLocaleString('vi-VN', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' }),
    }))
    setDocs((ds) => [...created, ...ds])
    setSelectedId(created[0].id)
    created.forEach((d) => processDoc(d.id))
    notify(`Đã tải lên ${created.length} văn bản`)
  }

  function approve(d: LegalDoc) {
    update(d.id, { step: 5, status: 'Đã lập chỉ mục' })
    notify(`Đã xuất bản “${d.name}”`)
  }

  function testQuery() {
    if (!query.trim()) return
    setQuerying(true)
    setResult(null)
    window.setTimeout(() => {
      setResult({
        lf: [
          `Step1: get_spo(s=HànhVi:"${query.slice(0, 32)}", p=bịXửPhạtTheo, o=Điều)`,
          'Step2: get_spo(s=o1, p=quyĐịnhMứcPhạt, o=ChếTài)',
          `Step3: Retrieval(rc, top_k=${config.rcTopK}, score_threshold=${config.rcScoreThreshold})`,
          'Step4: Output(o2) · llm_index_generator',
        ],
        nodes: ['NĐ 168/2024 › Điều 7', 'Khoản 7 › Điểm c', 'ChếTài: Phạt tiền', 'ChếTài: Trừ điểm GPLX'],
        answer: 'Hành vi được quy định tại Điều 7 NĐ 168/2024/NĐ-CP; mức phạt và hình thức bổ sung lấy từ Khoản 7 Điểm c.',
      })
      setQuerying(false)
    }, 1100)
  }

  return (
    <Page
      title="Văn bản & tri thức KAG"
      subtitle={`${docs.length} văn bản · ${docs.reduce((a, d) => a + d.entities, 0).toLocaleString('vi-VN')} thực thể trong đồ thị`}
      actions={
        <>
          <Button onClick={() => setUrlOpen(true)}>Dán đường dẫn</Button>
          <Button onClick={() => nav('/admin/imports?type=documents')}>Nhập danh mục</Button>
          <Button variant="primary" onClick={() => fileRef.current?.click()}>Tải văn bản lên</Button>
          <input
            ref={fileRef}
            type="file"
            multiple
            accept=".pdf,.doc,.docx,.md"
            className="hidden"
            onChange={(e) => {
              const files = Array.from(e.target.files ?? [])
              if (files.length) addDocs(files.map((f) => f.name))
              e.target.value = ''
            }}
          />
        </>
      }
    >
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-4 min-w-0">
          <div className="flex flex-wrap gap-1.5">
            {(['all', 'Đã lập chỉ mục', 'Chờ duyệt', 'Đang xử lý', 'Lưu trữ'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`rounded-full px-3 py-1 text-xs font-medium border transition-colors ${filter === f ? 'bg-navy text-bg border-navy' : 'border-line text-text-secondary hover:bg-selected'}`}
              >
                {f === 'all' ? 'Tất cả' : f}
              </button>
            ))}
          </div>

          <Card className="overflow-x-auto">
            <table className="w-full min-w-[640px]">
              <thead className="border-b border-line">
                <tr>
                  <Th>Văn bản</Th><Th>Loại</Th><Th>Hiệu lực</Th><Th>Trạng thái</Th><Th className="text-right">Thao tác</Th>
                </tr>
              </thead>
              <tbody>
                {shown.map((d) => (
                  <tr
                    key={d.id}
                    onClick={() => setSelectedId(d.id)}
                    className={`border-b border-line/60 last:border-0 cursor-pointer transition-colors ${d.id === selectedId ? 'bg-selected/60' : 'hover:bg-bg'}`}
                  >
                    <Td className="font-medium text-navy">
                      {d.name}
                      <span className="block text-[11.5px] font-normal text-muted">{d.chunks} đoạn · {d.entities} thực thể</span>
                    </Td>
                    <Td className="text-muted">{d.type}</Td>
                    <Td className="text-muted">{d.effective}</Td>
                    <Td><Badge tone={statusTone[d.status]}>{d.status}</Badge></Td>
                    <Td className="text-right whitespace-nowrap" >
                      <span onClick={(e) => e.stopPropagation()} className="inline-flex gap-1">
                        {d.status === 'Chờ duyệt' && <Button size="sm" variant="primary" onClick={() => approve(d)}>Duyệt</Button>}
                        {(d.status === 'Đã lập chỉ mục' || d.status === 'Lỗi' || d.status === 'Chờ xử lý') && (
                          <Button size="sm" variant="ghost" onClick={() => processDoc(d.id)}>Lập chỉ mục lại</Button>
                        )}
                        {d.status !== 'Lưu trữ' && d.status !== 'Đang xử lý' && (
                          <Button size="sm" variant="ghost" onClick={() => { update(d.id, { status: 'Lưu trữ', effective: 'Hết hiệu lực' }); notify('Đã lưu trữ văn bản') }}>Lưu trữ</Button>
                        )}
                        <Button size="sm" variant="danger" onClick={() => { setDocs((ds) => ds.filter((x) => x.id !== d.id)); notify('Đã xoá văn bản') }}>Xoá</Button>
                      </span>
                    </Td>
                  </tr>
                ))}
                {!shown.length && (
                  <tr><Td className="text-center text-muted py-8">Không có văn bản.</Td></tr>
                )}
              </tbody>
            </table>
          </Card>

          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragOver(false)
              const files = Array.from(e.dataTransfer.files)
              if (files.length) addDocs(files.map((f) => f.name))
            }}
            onClick={() => fileRef.current?.click()}
            className={`rounded-2xl border-2 border-dashed flex flex-col items-center justify-center gap-1 py-8 transition-colors cursor-pointer ${
              dragOver ? 'border-accent bg-selected/50' : 'border-line bg-surface hover:border-progress'
            }`}
          >
            <span className="text-2xl text-accent-strong" aria-hidden>⇪</span>
            <span className="text-sm font-medium text-navy">Kéo thả PDF / DOCX / MD vào đây</span>
            <span className="text-xs text-muted">Văn bản sẽ tự chạy qua reader → splitter → extractor → vectorizer</span>
          </div>
        </div>

        <div className="space-y-4">
          <Card title="Pipeline xử lý" right={selected && <span className="text-[11.5px] text-muted truncate max-w-[140px]">{selected.name}</span>}>
            <div className="px-5 pb-5">
              {selected ? (
                <>
                  <Progress value={(selected.step / 5) * 100} tone={selected.step >= 5 ? 'green' : 'accent'} />
                  <ol className="mt-4 space-y-3">
                    {pipelineSteps.map((label, i) => {
                      const done = selected.step > i
                      const active = selected.step === i && selected.status !== 'Lưu trữ'
                      return (
                        <li key={label} className="flex items-start gap-3">
                          <span className={`w-6 h-6 rounded-full shrink-0 grid place-items-center text-[11px] font-bold ${done ? 'bg-emerald-500 text-white' : active ? 'bg-accent text-navy ring-4 ring-accent/20' : 'bg-line text-muted'}`}>
                            {done ? '✓' : i + 1}
                          </span>
                          <span className={`text-[13px] pt-0.5 ${done || active ? 'text-navy' : 'text-muted'} ${active ? 'font-semibold' : ''}`}>{label}</span>
                        </li>
                      )
                    })}
                  </ol>
                  {selected.status === 'Chờ duyệt' && (
                    <Button variant="dark" className="mt-4 w-full" onClick={() => approve(selected)}>Duyệt & xuất bản</Button>
                  )}
                </>
              ) : (
                <p className="text-sm text-muted">Chọn văn bản để xem tiến trình.</p>
              )}
            </div>
          </Card>

          <Card title="Thử truy vấn">
            <div className="px-5 pb-5">
              <div className="flex gap-2">
                <input
                  className={inputCls}
                  placeholder="VD: vượt đèn đỏ xe máy"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && testQuery()}
                />
                <Button variant="dark" onClick={testQuery} disabled={!query.trim() || querying}>Chạy</Button>
              </div>
              <div className="mt-3 rounded-xl bg-bg border border-line p-3 min-h-24 text-xs leading-relaxed">
                {querying && <p className="text-muted animate-pulse">Đang suy luận trên đồ thị…</p>}
                {!querying && !result && <p className="text-muted">Kết quả gồm logical form, các nút đồ thị được dùng và câu trả lời.</p>}
                {result && (
                  <div className="space-y-3">
                    <div>
                      <p className="mb-1 font-semibold text-navy">Logical form</p>
                      {result.lf.map((l) => <p key={l} className="font-mono text-[11px] text-text-secondary">{l}</p>)}
                    </div>
                    <div>
                      <p className="mb-1 font-semibold text-navy">Nút đồ thị</p>
                      <div className="flex flex-wrap gap-1">{result.nodes.map((n) => <Badge key={n} tone="gold">{n}</Badge>)}</div>
                    </div>
                    <div>
                      <p className="mb-1 font-semibold text-navy">Câu trả lời</p>
                      <p className="text-text-secondary">{result.answer}</p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </Card>
        </div>
      </div>

      <Modal
        open={urlOpen}
        title="Nhập văn bản từ đường dẫn"
        onClose={() => setUrlOpen(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setUrlOpen(false)}>Huỷ</Button>
            <Button
              variant="primary"
              disabled={!url.trim()}
              onClick={() => {
                const name = decodeURIComponent(url.split('/').filter(Boolean).pop() ?? 'Văn bản mới').replace(/[-_]/g, ' ')
                addDocs([name])
                setUrl('')
                setUrlOpen(false)
              }}
            >
              Nhập & xử lý
            </Button>
          </>
        }
      >
        <Field label="Đường dẫn văn bản" hint="Hỗ trợ thuvienphapluat.vn, vbpl.vn hoặc liên kết PDF trực tiếp.">
          <input className={inputCls} value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://vbpl.vn/…/nghi-dinh-168-2024" autoFocus />
        </Field>
      </Modal>
    </Page>
  )
}
