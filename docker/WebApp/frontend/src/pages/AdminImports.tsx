import { useEffect, useMemo, useState } from 'react'
import JSZip from 'jszip'
import { useSearchParams } from 'react-router-dom'
import { useAdmin, type QBankItem, type LegalDoc } from '../admin/store'
import { Button, Card, Field, Page, Td, Th } from '../admin/ui'
import { mergeRecords, parseCsv, samples, tableObjects, validateRows, type ImportKind, type PreviewRow, type SignRecord } from '../admin/import-data'

const titles: Record<ImportKind, string> = { signs: 'Biển báo', questions: 'Ngân hàng câu hỏi', documents: 'Thông tin văn bản' }
const keyOfSign = (s: SignRecord) => s.code
const keyOfId = (s: QBankItem | LegalDoc) => s.id
const maxFileSize = 20 * 1024 * 1024

function readZipImage(entry: JSZip.JSZipObject): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const chunks: Uint8Array<ArrayBuffer>[] = []
    let size = 0
    // JSZip exposes this method at runtime but omits it from JSZipObject's typings.
    const stream = (entry as JSZip.JSZipObject & { internalStream(type: 'uint8array'): JSZip.JSZipStreamHelper<Uint8Array> }).internalStream('uint8array')
    stream.on('data', (chunk) => {
      size += chunk.length
      if (size > 5 * 1024 * 1024) { stream.pause(); reject(new Error(`Ảnh ${entry.name} vượt 5 MB sau giải nén.`)); return }
      chunks.push(new Uint8Array(chunk))
    }).on('error', reject).on('end', () => resolve(new Blob(chunks))).resume()
  })
}

export default function AdminImports() {
  const [params, setParams] = useSearchParams()
  const kind: ImportKind = params.get('type') === 'questions' ? 'questions' : params.get('type') === 'documents' ? 'documents' : 'signs'
  const { signs, setSigns, qbank, setQbank, docs, setDocs, notify } = useAdmin()
  const [rows, setRows] = useState<PreviewRow[]>([])
  const [images, setImages] = useState<Record<string, string>>({})
  const [fileName, setFileName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [update, setUpdate] = useState(false)
  const [confirmed, setConfirmed] = useState(false)
  const [message, setMessage] = useState('')
  const existing = kind === 'signs' ? signs.map(keyOfSign) : kind === 'questions' ? qbank.map(keyOfId) : docs.map(keyOfId)
  const existingKeys = new Set(existing.map((key) => key.toUpperCase()))
  const valid = rows.filter((row) => row.record)
  const duplicates = valid.filter((row) => existingKeys.has(row.key.toUpperCase()))
  const candidates = valid.filter((row) => update || !existingKeys.has(row.key.toUpperCase()))
  const unmatched = useMemo(() => Object.keys(images).filter((code) => ![...signs.map(keyOfSign), ...valid.map((r) => r.key)].some((key) => key.toUpperCase() === code)), [images, signs, rows])
  const imageMatches = signs.filter((sign) => images[sign.code.toUpperCase()])

  function switchKind(next: ImportKind) {
    setParams({ type: next })
  }

  useEffect(() => {
    setRows([]); setImages({}); setError(''); setMessage(''); setFileName(''); setConfirmed(false); setUpdate(false)
  }, [kind])

  function downloadSample() {
    const url = URL.createObjectURL(new Blob(['\uFEFF' + samples[kind]], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a'); link.href = url; link.download = `${kind}-template.csv`; link.click(); URL.revokeObjectURL(url)
  }

  async function readData(file?: File) {
    if (!file) return
    setRows([]); setError(''); setMessage(''); setConfirmed(false); setFileName(file.name); setBusy(true)
    try {
      if (file.size > maxFileSize) throw new Error('Tệp dữ liệu tối đa 20 MB.')
      let input: unknown
      if (/\.xlsx$/i.test(file.name)) {
        const { readSheet } = await import('read-excel-file/browser')
        input = tableObjects(await readSheet(file))
      } else if (/\.csv$/i.test(file.name)) input = tableObjects(parseCsv(await file.text()))
      else if (/\.json$/i.test(file.name)) input = JSON.parse(await file.text())
      else throw new Error('Chọn CSV, Excel .xlsx hoặc JSON; tệp Excel .xls cần chuyển sang .xlsx.')
      const next = validateRows(kind, input)
      if (!next.length) throw new Error('Tệp không có dòng dữ liệu.')
      setRows(next)
    } catch (e) { setError(e instanceof Error ? e.message : 'Không đọc được tệp.') }
    finally { setBusy(false) }
  }

  async function readImages(file?: File) {
    if (!file) return
    setError(''); setMessage(''); setImages({}); setConfirmed(false); setBusy(true)
    try {
      if (file.size > maxFileSize) throw new Error('ZIP ảnh tối đa 20 MB.')
      const zip = await JSZip.loadAsync(await file.arrayBuffer())
      const entries = Object.values(zip.files).filter((entry) => !entry.dir && !entry.name.startsWith('__MACOSX/'))
      if (entries.length > 1000) throw new Error('ZIP tối đa 1.000 tệp.')
      const next: Record<string, string> = {}
      let total = 0
      for (const entry of entries) {
        if (!/\.(png|jpe?g|webp)$/i.test(entry.name)) throw new Error(`Ảnh ${entry.name}: chỉ hỗ trợ PNG, JPEG, WebP. SVG cần được xử lý an toàn ở backend.`)
        const code = entry.name.split('/').pop()!.replace(/\.[^.]+$/, '').toUpperCase()
        if (!/^[A-Z0-9._-]+$/.test(code) || next[code]) throw new Error(`Tên ảnh không hợp lệ hoặc trùng mã: ${entry.name}`)
        const blob = await readZipImage(entry)
        total += blob.size
        if (blob.size > 5 * 1024 * 1024 || total > 50 * 1024 * 1024) throw new Error('Mỗi ảnh tối đa 5 MB, tổng ảnh giải nén tối đa 50 MB.')
        const bitmap = await createImageBitmap(blob)
        if (bitmap.width > 4096 || bitmap.height > 4096) { bitmap.close(); throw new Error(`Ảnh ${entry.name} vượt 4.096 pixel.`) }
        bitmap.close()
        next[code] = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = () => reject(new Error('Không đọc được ảnh')); reader.readAsDataURL(blob)
        })
      }
      if (!Object.keys(next).length) throw new Error('ZIP không có ảnh.')
      setImages(next)
    } catch (e) { setError(e instanceof Error ? e.message : 'Không đọc được ZIP ảnh.') }
    finally { setBusy(false) }
  }

  function confirmImport() {
    if (!candidates.length || confirmed) return
    if (kind === 'signs') setSigns((current) => mergeRecords(current, candidates.map((row) => {
      const sign = row.record as SignRecord
      return { ...sign, image: images[sign.code] ?? current.find((s) => s.code === sign.code)?.image }
    }), keyOfSign, update))
    else if (kind === 'questions') setQbank((current) => mergeRecords(current, candidates.map((r) => r.record as QBankItem), keyOfId, update))
    else setDocs((current) => mergeRecords(current, candidates.map((r) => r.record as LegalDoc), keyOfId, update))
    setConfirmed(true)
    setMessage(`Đã nhập ${candidates.length} bản ghi vào dữ liệu demo. ${rows.length - valid.length} dòng lỗi không được nhập.`)
    notify('Đã nhập dữ liệu để kiểm duyệt')
  }

  function attachImages() {
    setSigns((current) => current.map((sign) => images[sign.code.toUpperCase()] ? { ...sign, image: images[sign.code.toUpperCase()] } : sign))
    setMessage(`Đã ghép ảnh cho ${imageMatches.length} biển báo trong dữ liệu demo.`)
    setImages({})
  }

  return (
    <Page title="Nhập dữ liệu" subtitle="Kiểm tra dữ liệu trước khi nhập; bổ sung ảnh biển báo khi đã thu thập đủ." actions={<Button onClick={downloadSample}>Tải CSV mẫu</Button>}>
      <div className="flex flex-wrap gap-6 border-b border-line mb-6" role="tablist" aria-label="Loại dữ liệu">
        {(Object.keys(titles) as ImportKind[]).map((key) => <button key={key} role="tab" aria-selected={kind === key} disabled={busy} onClick={() => switchKind(key)} className={`pb-3 text-sm cursor-pointer border-b-2 focus-visible:outline-2 focus-visible:outline-accent-strong ${kind === key ? 'border-navy text-navy font-semibold' : 'border-transparent text-muted hover:text-navy'}`}>{titles[key]}</button>)}
      </div>
      <p className="mb-5 text-sm text-muted">Dữ liệu demo lưu trong phiên quản trị, mất khi tải lại trang hoặc đăng xuất. Chưa xuất bản cho người dùng.</p>
      <div className="grid gap-6 lg:grid-cols-2 mb-6">
        <Card title="1. Chọn tệp dữ liệu"><div className="px-5 pb-5 space-y-4">
          <Field label="CSV / Excel .xlsx / JSON" hint="Excel đọc sheet đầu tiên. Dòng đầu là tên cột theo CSV mẫu."><input key={kind} aria-label="Tệp dữ liệu" type="file" onClick={(e) => { e.currentTarget.value = '' }} accept=".csv,.xlsx,.json" disabled={busy} onChange={(e) => { void readData(e.target.files?.[0]) }} className="block w-full text-sm file:mr-3 file:rounded-md file:border file:border-navy/35 file:bg-selected file:px-3 file:py-2 file:cursor-pointer" /></Field>
          <p className="text-xs leading-6 text-muted">{kind === 'signs' ? 'Cột: code, name, group, meaning, source. Mã biển là khóa để ghép ảnh.' : kind === 'questions' ? 'Cột: id, chapter, question, option1…option4, answer, critical, explanation, source. CSV/Excel: answer từ 1. JSON dùng định dạng Xuất JSON: answer từ 0.' : 'Cột: id, name, type, effective (YYYY-MM-DD). Chỉ nhập thông tin văn bản; tải nội dung PDF/DOCX ở Văn bản & tri thức KAG.'}</p>
          <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={update} disabled={busy || confirmed} onChange={(e) => setUpdate(e.target.checked)} className="mt-1 accent-[var(--color-accent-strong)]" />Cập nhật bản ghi đã có cùng mã; mặc định bỏ qua</label>
        </div></Card>
        {kind === 'signs' ? <Card title="2. Ghép ảnh theo mã biển"><div className="px-5 pb-5 space-y-4">
          <Field label="ZIP ảnh PNG / JPEG / WebP" hint="Ví dụ: images/P.102.png. Tên ảnh phải khớp mã biển, không phân biệt hoa/thường."><input aria-label="ZIP ảnh biển báo" type="file" onClick={(e) => { e.currentTarget.value = '' }} accept=".zip" disabled={busy} onChange={(e) => { void readImages(e.target.files?.[0]) }} className="block w-full text-sm file:mr-3 file:rounded-md file:border file:border-navy/35 file:bg-selected file:px-3 file:py-2 file:cursor-pointer" /></Field>
          <p className="text-sm text-muted">Có thể nhập danh mục trước, ghép ảnh sau. Biển thiếu ảnh vẫn được lưu để bổ sung.</p>
          {Object.keys(images).length > 0 && <p className="text-sm">{Object.keys(images).length} ảnh · {imageMatches.length} khớp danh mục đã nhập · {unmatched.length} chưa có mã tương ứng</p>}
          {unmatched.length > 0 && <p className="text-xs text-amber-700 break-words">Chưa khớp: {unmatched.join(', ')}</p>}
          <Button disabled={busy || !imageMatches.length} onClick={attachImages}>Ghép ảnh vào danh mục đã nhập</Button>
        </div></Card> : <Card title="Chuẩn hóa và kiểm duyệt"><div className="px-5 pb-5 text-sm text-muted leading-7">Các dòng lỗi cần sửa trong tệp rồi tải lại. Trùng mã trong cùng tệp được đánh dấu lỗi. Dữ liệu nhập chưa được xác minh với nguồn chính thức. Trích xuất nội dung/ảnh từ PDF và kiểm duyệt xuất bản sẽ kết nối dịch vụ Python và backend sau.</div></Card>}
      </div>
      {busy && <p role="status" className="mb-4 text-sm">Đang đọc và kiểm tra tệp…</p>}
      {error && <p role="alert" className="mb-4 text-sm text-red-700">{error}</p>}
      {message && <p role="status" className="mb-4 text-sm text-emerald-700">{message}</p>}
      <Card title="Xem trước dữ liệu" right={<span className="text-xs text-muted">{fileName || 'Chưa chọn tệp'}</span>}>
        {!rows.length ? <p className="px-5 pb-6 text-sm text-muted">Chọn tệp để xem các dòng hợp lệ, lỗi và mã trùng trước khi xác nhận.</p> : <>
          <p className="px-5 pb-4 text-sm text-muted">{rows.length} dòng · {valid.length} hợp lệ · {rows.length - valid.length} lỗi · {duplicates.length} trùng danh mục</p>
          <div className="overflow-x-auto max-h-96"><table className="w-full min-w-[640px]"><thead><tr><Th>Dòng</Th><Th>Mã</Th><Th>Nội dung</Th>{kind === 'signs' && <Th>Ảnh</Th>}<Th>Kết quả kiểm tra</Th></tr></thead><tbody>
            {rows.map((row) => <tr key={row.line} className="border-t border-line"><Td>{row.line}</Td><Td>{row.key || '—'}</Td><Td>{row.title || '—'}</Td>{kind === 'signs' && <Td>{images[row.key.toUpperCase()] ? <img src={images[row.key.toUpperCase()]} alt={`Biển ${row.key}`} className="w-12 h-12 object-contain" /> : <span className="text-muted">{signs.find((s) => s.code === row.key.toUpperCase())?.image ? 'Giữ ảnh hiện có' : 'Chưa có ảnh'}</span>}</Td>}<Td><span className={row.errors.length ? 'text-red-700' : 'text-text-secondary'}>{row.errors.length ? row.errors.join('; ') : existingKeys.has(row.key.toUpperCase()) ? update ? 'Sẽ cập nhật' : 'Bỏ qua mã đã có' : 'Sẽ thêm mới'}</span></Td></tr>)}
          </tbody></table></div>
          <div className="p-5 flex flex-wrap items-center gap-4"><Button variant="dark" disabled={busy || !!error || !candidates.length || confirmed} onClick={confirmImport}>{confirmed ? 'Đã nhập' : `Xác nhận nhập ${candidates.length} dòng hợp lệ`}</Button><span className="text-xs text-muted">Dòng lỗi không được nhập.</span></div>
        </>}
      </Card>
      {kind === 'signs' && <Card title={`Danh mục biển báo đã nhập (${signs.length})`} className="mt-6">
        <div className="max-h-96 overflow-x-auto"><table className="w-full min-w-[600px]"><thead><tr><Th>Ảnh</Th><Th>Mã / Tên</Th><Th>Nhóm</Th><Th>Ý nghĩa / Nguồn</Th></tr></thead><tbody>{signs.map((sign) => <tr key={sign.code} className="border-t border-line"><Td>{sign.image ? <img src={sign.image} alt={sign.name} className="w-12 h-12 object-contain" /> : <span className="text-muted">Thiếu ảnh</span>}</Td><Td><strong>{sign.code}</strong><p>{sign.name}</p></Td><Td>{sign.group}</Td><Td>{sign.meaning}<p className="mt-1 text-xs text-muted">{sign.source}</p></Td></tr>)}</tbody></table>{!signs.length && <p className="px-5 pb-5 text-sm text-muted">Chưa nhập biển báo. Có thể bắt đầu bằng danh mục chưa có ảnh.</p>}</div>
      </Card>}
    </Page>
  )
}

