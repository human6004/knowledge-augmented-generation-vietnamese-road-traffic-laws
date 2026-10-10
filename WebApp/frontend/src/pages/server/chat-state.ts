import { api, send, ApiError } from '../../api.ts'

type Citation = { doc_id: string; unit_id: string; quote: string }
type ChatRecord = { id: string; question: string; answer: string; state: string; citations: Citation[] }
type ChatState = { rows: ChatRecord[]; loading: boolean; error: string; busy: boolean; requestError: string; observed: 'idle' | 'answered' | 'unavailable' | 'offline' | 'error' }

function record(value: unknown): value is ChatRecord {
  if (!value || typeof value !== 'object') return false
  const row = value as ChatRecord
  return typeof row.id === 'string' && !!row.id && typeof row.question === 'string' && typeof row.answer === 'string' && typeof row.state === 'string' && Array.isArray(row.citations)
}

export function chatView(row: ChatRecord) {
  const empty = { answer: '', citations: [] as Citation[] }
  if (row.state === 'UNAVAILABLE') return { status: 'Chưa có câu trả lời — dịch vụ KAG chưa khả dụng.', ...empty }
  if (row.state === 'PROCESSING') return { status: 'Đang xử lý — chưa có câu trả lời.', ...empty }
  const citationsValid = row.citations.length > 0 && row.citations.length <= 20 && row.citations.every(c => c && ['doc_id', 'unit_id', 'quote'].every(key => typeof c[key as keyof Citation] === 'string' && c[key as keyof Citation].trim()))
  if (row.state !== 'ANSWERED' || !row.answer.trim() || !citationsValid) return { status: 'Chưa có câu trả lời đủ căn cứ.', ...empty }
  return { status: 'Đã trả lời', answer: row.answer, citations: row.citations }
}

export function createChat() {
  let state: ChatState = { rows: [], loading: true, error: '', busy: false, requestError: '', observed: 'idle' }
  const listeners = new Set<() => void>()
  let history: Promise<void> | undefined
  function update(change: Partial<ChatState>) { state = { ...state, ...change }; listeners.forEach(listener => listener()) }
  function load(): Promise<void> {
    if (history) return history
    update({ loading: true, error: '' })
    history = api<unknown>('/chat').then(rows => {
      if (!Array.isArray(rows) || !rows.every(record)) throw new ApiError('Invalid history', 502)
      update({ rows })
    }).catch(error => {
      const status = error instanceof ApiError ? error.status : -1
      update({ error: status === 0 ? 'Không kết nối được backend. Hãy thử lại.' : status === 401 ? 'Phiên đã hết hạn. Vui lòng đăng nhập lại.' : 'Không tải được lịch sử. Hãy thử lại.', ...(status === 401 ? { rows: [] } : {}) })
    }).finally(() => { history = undefined; update({ loading: false }) })
    return history
  }
  async function submit(message: string) {
    if (state.busy || state.loading || !message.trim() || message.length > 4000) return false
    update({ busy: true, requestError: '' })
    try {
      const row = await api<unknown>('/chat', send('POST', { message }))
      if (!record(row)) throw new ApiError('Invalid chat response', 502)
      const view = chatView(row)
      update({ rows: [row, ...state.rows.filter(old => old.id !== row.id)].slice(0, 50), observed: view.answer ? 'answered' : row.state === 'UNAVAILABLE' ? 'unavailable' : 'error' })
      return true
    } catch (error) {
      const status = error instanceof ApiError ? error.status : -1
      update({ observed: status === 503 ? 'unavailable' : status === 0 ? 'offline' : 'error', requestError: status === 503 ? 'Dịch vụ KAG chưa khả dụng. Câu hỏi chưa có câu trả lời.' : status === 0 ? 'Không kết nối được backend. Câu hỏi chưa được xác nhận; hãy thử lại.' : status === 401 ? 'Phiên đã hết hạn. Vui lòng đăng nhập lại.' : status === 403 ? 'Bạn không có quyền gửi câu hỏi.' : status === 422 || status === 400 ? 'Câu hỏi không hợp lệ. Hãy kiểm tra nội dung.' : 'Không gửi được câu hỏi. Hãy thử lại.', ...(status === 401 ? { rows: [] } : {}) })
      // Backend saves UNAVAILABLE before returning 503; read that row once.
      if (status === 503) await load()
      return false
    } finally { update({ busy: false }) }
  }
  return { getSnapshot: () => state, subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener) } }, load, submit }
}
