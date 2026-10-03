import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAdmin, type QBankItem } from '../admin/store'
import { Badge, Button, Card, Field, Modal, Page, Td, Th, Toggle, inputCls } from '../admin/ui'

const chapters = ['Khái niệm và quy tắc', 'Văn hoá giao thông', 'Kỹ thuật lái xe', 'Cấu tạo sửa chữa', 'Biển báo đường bộ', 'Sa hình']
const blank = (): QBankItem => ({ id: '', chapter: chapters[0], question: '', options: ['', '', ''], answer: 0, critical: false, explanation: '', source: '' })

export default function AdminQuestions() {
  const nav = useNavigate()
  const { qbank, setQbank, notify } = useAdmin()
  const [q, setQ] = useState('')
  const [chapter, setChapter] = useState('all')
  const [onlyCritical, setOnlyCritical] = useState(false)
  const [editing, setEditing] = useState<QBankItem | null>(null)
  const [generating, setGenerating] = useState(false)

  const shown = useMemo(
    () => qbank.filter((x) => (chapter === 'all' || x.chapter === chapter) && (!onlyCritical || x.critical) && x.question.toLowerCase().includes(q.toLowerCase())),
    [qbank, chapter, onlyCritical, q]
  )

  function save() {
    if (!editing || !editing.question.trim()) return
    if (editing.id) setQbank((xs) => xs.map((x) => (x.id === editing.id ? editing : x)))
    else setQbank((xs) => [{ ...editing, id: 'q' + Date.now() }, ...xs])
    notify(editing.id ? 'Đã cập nhật câu hỏi' : 'Đã thêm câu hỏi')
    setEditing(null)
  }

  function generate() {
    setGenerating(true)
    window.setTimeout(() => {
      const gen: QBankItem[] = [
        { id: 'g' + Date.now(), chapter: 'Khái niệm và quy tắc', question: 'Xe mô tô vượt đèn đỏ bị trừ bao nhiêu điểm GPLX?', options: ['2 điểm', '4 điểm', '6 điểm'], answer: 1, critical: false, explanation: 'Sinh tự động từ NĐ 168/2024, Điều 7.', source: 'NĐ 168/2024 (KAG)' },
        { id: 'g' + Date.now() + 1, chapter: 'Khái niệm và quy tắc', question: 'Hành vi điều khiển xe khi có nồng độ cồn bị xử lý thế nào?', options: ['Nhắc nhở', 'Phạt tiền và tước GPLX', 'Chỉ phạt tiền'], answer: 1, critical: true, explanation: 'Sinh tự động từ đồ thị tri thức.', source: 'NĐ 168/2024 (KAG)' },
      ]
      setQbank((xs) => [...gen, ...xs])
      setGenerating(false)
      notify('KAG đã sinh 2 câu hỏi mới từ đồ thị')
    }, 1400)
  }

  function exportJson() {
    const blob = new Blob([JSON.stringify(qbank, null, 2)], { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'ngan-hang-cau-hoi.json'
    a.click()
  }

  return (
    <Page
      title="Ngân hàng câu hỏi"
      subtitle={`${qbank.length} câu · ${qbank.filter((x) => x.critical).length} câu điểm liệt`}
      actions={
        <>
          <Button onClick={exportJson}>Xuất JSON</Button>
          <Button onClick={() => nav('/admin/imports?type=questions')}>Nhập hàng loạt</Button>
          <Button onClick={generate} disabled={generating}>{generating ? 'Đang sinh…' : '✻ Sinh câu hỏi từ KAG'}</Button>
          <Button variant="primary" onClick={() => setEditing(blank())}>+ Thêm câu hỏi</Button>
        </>
      }
    >
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <input className={`${inputCls} max-w-xs`} placeholder="Tìm câu hỏi…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className={`${inputCls} max-w-[220px]`} value={chapter} onChange={(e) => setChapter(e.target.value)} aria-label="Chương">
          <option value="all">Tất cả chương</option>
          {chapters.map((c) => <option key={c}>{c}</option>)}
        </select>
        <label className="flex items-center gap-2 text-[13px] text-text-secondary">
          <Toggle checked={onlyCritical} onChange={setOnlyCritical} label="Chỉ câu điểm liệt" /> Chỉ câu điểm liệt
        </label>
      </div>

      <Card className="overflow-x-auto">
        <table className="w-full min-w-[720px]">
          <thead className="border-b border-line">
            <tr><Th className="w-12">#</Th><Th>Câu hỏi</Th><Th>Chương</Th><Th>Nguồn</Th><Th className="text-right">Thao tác</Th></tr>
          </thead>
          <tbody>
            {shown.map((x, i) => (
              <tr key={x.id} className="border-b border-line/60 last:border-0 hover:bg-bg">
                <Td className="text-muted font-mono text-xs">{i + 1}</Td>
                <Td className="text-navy">
                  <span className="font-medium">{x.question}</span>
                  {x.critical && <span className="ml-2"><Badge tone="red">Điểm liệt</Badge></span>}
                  <span className="block mt-0.5 text-[12px] text-muted">Đáp án: {x.options[x.answer]}</span>
                </Td>
                <Td className="text-muted whitespace-nowrap">{x.chapter}</Td>
                <Td className="text-muted">{x.source}</Td>
                <Td className="text-right whitespace-nowrap">
                  <Button size="sm" variant="ghost" onClick={() => setEditing({ ...x, options: [...x.options] })}>Sửa</Button>
                  <Button size="sm" variant="danger" onClick={() => { setQbank((xs) => xs.filter((y) => y.id !== x.id)); notify('Đã xoá câu hỏi') }}>Xoá</Button>
                </Td>
              </tr>
            ))}
            {!shown.length && <tr><Td className="py-8 text-center text-muted">Không có câu hỏi phù hợp.</Td></tr>}
          </tbody>
        </table>
      </Card>

      <Modal
        open={!!editing}
        title={editing?.id ? 'Sửa câu hỏi' : 'Thêm câu hỏi'}
        onClose={() => setEditing(null)}
        footer={<><Button variant="ghost" onClick={() => setEditing(null)}>Huỷ</Button><Button variant="primary" onClick={save} disabled={!editing?.question.trim()}>Lưu</Button></>}
      >
        {editing && (
          <div className="space-y-4">
            <Field label="Nội dung câu hỏi">
              <textarea rows={2} className={inputCls} value={editing.question} onChange={(e) => setEditing({ ...editing, question: e.target.value })} />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Chương">
                <select className={inputCls} value={editing.chapter} onChange={(e) => setEditing({ ...editing, chapter: e.target.value })}>
                  {chapters.map((c) => <option key={c}>{c}</option>)}
                </select>
              </Field>
              <Field label="Căn cứ">
                <input className={inputCls} value={editing.source} onChange={(e) => setEditing({ ...editing, source: e.target.value })} placeholder="NĐ 168/2024…" />
              </Field>
            </div>
            <div>
              <span className="block text-xs font-medium text-text-secondary mb-1.5">Phương án (chọn đáp án đúng)</span>
              <div className="space-y-2">
                {editing.options.map((o, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <input type="radio" name="ans" checked={editing.answer === i} onChange={() => setEditing({ ...editing, answer: i })} className="accent-[var(--color-accent-strong)]" aria-label={`Đáp án ${i + 1}`} />
                    <input className={inputCls} value={o} placeholder={`Phương án ${i + 1}`} onChange={(e) => setEditing({ ...editing, options: editing.options.map((v, k) => (k === i ? e.target.value : v)) })} />
                    {editing.options.length > 2 && (
                      <button className="text-muted hover:text-red-600 px-1" aria-label="Xoá phương án" onClick={() => setEditing({ ...editing, options: editing.options.filter((_, k) => k !== i), answer: 0 })}>✕</button>
                    )}
                  </div>
                ))}
              </div>
              {editing.options.length < 4 && (
                <button className="mt-2 text-xs font-medium text-accent-strong" onClick={() => setEditing({ ...editing, options: [...editing.options, ''] })}>+ Thêm phương án</button>
              )}
            </div>
            <Field label="Giải thích">
              <textarea rows={2} className={inputCls} value={editing.explanation} onChange={(e) => setEditing({ ...editing, explanation: e.target.value })} />
            </Field>
            <label className="flex items-center gap-2 text-[13px] text-navy">
              <Toggle checked={editing.critical} onChange={(v) => setEditing({ ...editing, critical: v })} label="Câu điểm liệt" /> Câu điểm liệt
            </label>
          </div>
        )}
      </Modal>
    </Page>
  )
}
