import type { LegalDoc, QBankItem } from './store'

export type ImportKind = 'signs' | 'questions' | 'documents'
export type SignRecord = { code: string; name: string; group: string; meaning: string; source: string; image?: string }
export type ImportRecord = SignRecord | QBankItem | LegalDoc
export type PreviewRow = { line: number; key: string; title: string; record?: ImportRecord; errors: string[] }

export const samples: Record<ImportKind, string> = {
  signs: 'code,name,group,meaning,source\nP.DEMO,Biển mẫu,Cấm,Nội dung cần kiểm duyệt,Nguồn cần bổ sung\n',
  questions: 'id,chapter,question,option1,option2,answer,critical,explanation,source\nDEMO-1,Khái niệm và quy tắc,Câu hỏi mẫu,Phương án 1,Phương án 2,1,false,Giải thích mẫu,Nguồn cần bổ sung\n',
  documents: 'id,name,type,effective\nDOC-DEMO,Văn bản mẫu,Nghị định,2025-01-01\n',
}

export function parseCsv(text: string): string[][] {
  const rows: string[][] = []
  let row: string[] = [], cell = '', quoted = false, closed = false
  text = text.replace(/^\uFEFF/, '')
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { cell += '"'; i++ }
      else if (c === '"') { quoted = false; closed = true }
      else cell += c
    } else if (c === '"') {
      if (cell || closed) throw new Error('Dấu ngoặc kép không hợp lệ trong CSV.')
      quoted = true
    } else if (c === ',' || c === '\n' || c === '\r') {
      row.push(cell); cell = ''; closed = false
      if (c !== ',') { rows.push(row); row = []; if (c === '\r' && text[i + 1] === '\n') i++ }
    } else {
      if (closed) throw new Error('Ký tự không hợp lệ sau dấu ngoặc kép.')
      cell += c
    }
  }
  if (quoted) throw new Error('CSV thiếu dấu ngoặc kép đóng.')
  if (cell || row.length || closed) { row.push(cell); rows.push(row) }
  return rows
}

export function tableObjects(rows: unknown[][]): Record<string, unknown>[] {
  const headers = (rows[0] ?? []).map((v) => String(v ?? '').trim())
  if (!headers.length || headers.some((h) => !h) || new Set(headers).size !== headers.length) throw new Error('Tên cột trống hoặc trùng. Hãy dùng tệp mẫu.')
  return rows.slice(1).map((row) => {
    if (row.length > headers.length) throw new Error('Số ô vượt quá số cột trong tiêu đề.')
    return Object.fromEntries(headers.map((h, i) => [h, row[i] ?? '']))
  })
}

export function validateRows(kind: ImportKind, input: unknown): PreviewRow[] {
  if (!Array.isArray(input) || input.length > 5000) throw new Error('Dữ liệu phải là danh sách tối đa 5.000 dòng.')
  const seen = new Set<string>()
  return input.map((item, index) => {
    const row = item && typeof item === 'object' && !Array.isArray(item) ? item as Record<string, unknown> : {}
    const text = (key: string) => typeof row[key] === 'string' || typeof row[key] === 'number' ? String(row[key]).trim() : ''
    const errors: string[] = []
    const key = text(kind === 'signs' ? 'code' : 'id')
    const title = text(kind === 'questions' ? 'question' : 'name')
    if (!key) errors.push('Thiếu mã')
    else if (seen.has(key.toUpperCase())) errors.push('Trùng mã trong tệp')
    else seen.add(key.toUpperCase())
    if (!title) errors.push('Thiếu nội dung/tên')
    let record: ImportRecord | undefined
    if (kind === 'signs') {
      if (key && !/^[a-z0-9._-]+$/i.test(key)) errors.push('Mã biển chỉ chứa chữ, số, dấu chấm, gạch ngang/gạch dưới')
      for (const [field, label] of [['group', 'nhóm biển'], ['meaning', 'ý nghĩa'], ['source', 'nguồn']]) if (!text(field)) errors.push(`Thiếu ${label}`)
      record = { code: key.toUpperCase(), name: title, group: text('group'), meaning: text('meaning'), source: text('source') }
    } else if (kind === 'questions') {
      const options = Array.isArray(row.options) ? row.options.map((v) => typeof v === 'string' ? v.trim() : '') : ['option1', 'option2', 'option3', 'option4'].map(text)
      if (!Array.isArray(row.options)) while (options.length && !options[options.length - 1]) options.pop()
      // JSON follows the existing export (zero-based); CSV/Excel uses answers 1–4.
      const rawAnswer = text('answer')
      const answer = rawAnswer === '' ? NaN : Number(rawAnswer) - (Array.isArray(row.options) ? 0 : 1)
      const critical = String(row.critical ?? '').toLowerCase()
      if (options.length < 2 || options.length > 4 || options.some((v) => !v)) errors.push('Cần 2–4 phương án không trống')
      if (!Number.isInteger(answer) || answer < 0 || answer >= options.length) errors.push('Đáp án ngoài phạm vi phương án')
      if (!['true', 'false', '1', '0'].includes(critical)) errors.push('critical phải là true/false hoặc 1/0')
      if (!text('chapter') || !text('source')) errors.push('Thiếu chương hoặc nguồn')
      record = { id: key, question: title, chapter: text('chapter'), options, answer, critical: critical === 'true' || critical === '1', explanation: text('explanation'), source: text('source') }
    } else {
      const type = text('type') as LegalDoc['type']
      const effective = row.effective instanceof Date ? row.effective.toISOString().slice(0, 10) : text('effective')
      if (!['Luật', 'Nghị định', 'Thông tư', 'Quyết định'].includes(type)) errors.push('Loại văn bản không hợp lệ')
      if (!/^\d{4}-\d{2}-\d{2}$/.test(effective) || Number.isNaN(Date.parse(effective)) || new Date(effective).toISOString().slice(0, 10) !== effective) errors.push('Ngày hiệu lực phải là YYYY-MM-DD hợp lệ')
      record = { id: key, name: title, type, effective, status: 'Chờ xử lý', chunks: 0, entities: 0, step: 0, updated: new Date().toLocaleString('vi-VN') }
    }
    return { line: index + 2, key, title, record: errors.length ? undefined : record, errors }
  })
}

export function mergeRecords<T>(existing: T[], incoming: T[], keyOf: (row: T) => string, update: boolean): T[] {
  const result = new Map(existing.map((row) => [keyOf(row).toUpperCase(), row]))
  for (const row of incoming) {
    const key = keyOf(row).toUpperCase()
    if (update || !result.has(key)) result.set(key, row)
  }
  return [...result.values()]
}
