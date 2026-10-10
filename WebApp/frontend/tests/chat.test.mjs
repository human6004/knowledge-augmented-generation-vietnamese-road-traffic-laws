import assert from 'node:assert/strict'
import { test, beforeEach } from 'node:test'
import { createChat, chatView } from '../src/pages/server/chat-state.ts'
import { tokenKey } from '../src/api.ts'

const citation = { doc_id: 'fixture-doc', unit_id: 'fixture-unit', quote: 'TEST ONLY — trích đoạn kiểm thử.\nKhông phải căn cứ pháp luật.' }
const answered = { id: 'fixture-chat', question: 'Câu hỏi tiếng Việt\nDòng thứ hai', answer: 'TEST ONLY — nội dung từ HTTP fixture.', citations: [citation], state: 'ANSWERED', createdAt: '2026-10-10T00:00:00Z' }
const unavailable = { ...answered, answer: '', citations: [], state: 'UNAVAILABLE' }
let requests, tokens, expired
const response = (body, status = 200) => new Response(JSON.stringify(body), { status })
beforeEach(() => {
  requests = []; tokens = new Map([[tokenKey, 'webapp-jwt-fixture']]); expired = false
  globalThis.sessionStorage = { getItem: key => tokens.get(key), removeItem: key => tokens.delete(key) }
  globalThis.window = { dispatchEvent: event => { expired = event.type === 'luatgt-session-expired' } }
})
function wire(handler) {
  globalThis.fetch = async (url, options) => {
    requests.push({ url, ...options })
    assert.equal(url, '/api/chat')
    assert.equal(options.headers.get('Authorization'), 'Bearer webapp-jwt-fixture')
    return handler(options.method || 'GET')
  }
}
async function loaded(handler = () => response([])) { wire(handler); const chat = createChat(); await chat.load(); return chat }

test('history loads once for concurrent mounts and preserves backend rows', async () => {
  let finish; wire(() => new Promise(resolve => { finish = resolve }))
  const chat = createChat(), first = chat.load(), second = chat.load()
  assert.equal(requests.length, 1); assert.equal(chat.getSnapshot().loading, true)
  finish(response([answered])); await Promise.all([first, second])
  assert.deepEqual(chat.getSnapshot().rows, [answered]); assert.equal(chat.getSnapshot().loading, false)
  assert.equal(chat.getSnapshot().observed, 'idle')
})
test('empty history is successful without fabricating a conversation', async () => {
  const chat = await loaded(); assert.deepEqual(chat.getSnapshot().rows, []); assert.equal(chat.getSnapshot().error, '')
})
test('history network error is visible and can be retried', async () => {
  const chat = await loaded(() => { throw new Error('offline') })
  assert.match(chat.getSnapshot().error, /Không kết nối/); assert.equal(chat.getSnapshot().loading, false)
  wire(() => response([unavailable])); await chat.load(); assert.deepEqual(chat.getSnapshot().rows, [unavailable]); assert.equal(chat.getSnapshot().error, '')
})
test('POST uses only WebApp JWT and message, preserves Vietnamese, and avoids history refetch', async () => {
  const chat = await loaded(method => response(method === 'POST' ? answered : []))
  assert.equal(await chat.submit(answered.question), true)
  assert.equal(requests.length, 2); assert.deepEqual(JSON.parse(requests[1].body), { message: answered.question })
  assert.deepEqual(chat.getSnapshot().rows, [answered]); assert.equal(chat.getSnapshot().observed, 'answered')
  assert.deepEqual(chatView(chat.getSnapshot().rows[0]), { status: 'Đã trả lời', answer: answered.answer, citations: [citation] })
})
test('503 refreshes persisted UNAVAILABLE once and never exposes backend error details', async () => {
  let gets = 0
  const chat = await loaded(method => method === 'POST' ? response({ message: 'KAG-secret-fixture /private/credentials' }, 503) : response(++gets === 1 ? [] : [unavailable]))
  assert.equal(await chat.submit(answered.question), false)
  assert.equal(requests.length, 3); assert.deepEqual(chat.getSnapshot().rows, [unavailable])
  assert.equal(chat.getSnapshot().observed, 'unavailable'); assert.match(chat.getSnapshot().requestError, /KAG chưa khả dụng/)
  assert.doesNotMatch(chat.getSnapshot().requestError, /KAG-secret-fixture|private/)
  assert.deepEqual(chatView(unavailable), { status: 'Chưa có câu trả lời — dịch vụ KAG chưa khả dụng.', answer: '', citations: [] })
  assert.equal(tokens.has(tokenKey), true); assert.equal(expired, false)
})
test('offline POST retains history and emits no answer or automatic retry', async () => {
  const chat = await loaded(method => { if (method === 'POST') throw new Error('offline'); return response([unavailable]) })
  assert.equal(await chat.submit(answered.question), false); assert.equal(requests.length, 2)
  assert.deepEqual(chat.getSnapshot().rows, [unavailable]); assert.equal(chat.getSnapshot().observed, 'offline'); assert.match(chat.getSnapshot().requestError, /Không kết nối/)
})
test('expired JWT clears session and chat without refreshing unauthenticated history', async () => {
  const chat = await loaded(method => response(method === 'POST' ? { message: 'Unauthorized' } : [unavailable], method === 'POST' ? 401 : 200))
  assert.equal(await chat.submit(answered.question), false)
  assert.equal(requests.length, 2); assert.equal(expired, true); assert.equal(tokens.has(tokenKey), false)
  assert.deepEqual(chat.getSnapshot().rows, []); assert.match(chat.getSnapshot().requestError, /đăng nhập/); assert.equal(chat.getSnapshot().observed, 'error')
})
test('rapid double submit sends only one POST', async () => {
  let finish; const chat = await loaded(method => method === 'POST' ? new Promise(resolve => { finish = resolve }) : response([]))
  const first = chat.submit(answered.question); assert.equal(chat.getSnapshot().busy, true)
  assert.equal(await chat.submit('Không gửi lần hai'), false); assert.equal(requests.length, 2)
  finish(response(answered)); assert.equal(await first, true); assert.equal(chat.getSnapshot().busy, false)
})
test('blank, over-limit, and submit during initial history load never send POST', async () => {
  const chat = await loaded(); await chat.submit(' \n '); await chat.submit('a'.repeat(4001)); assert.equal(requests.length, 1)
  let finish; wire(() => new Promise(resolve => { finish = resolve })); const other = createChat(), loading = other.load()
  assert.equal(await other.submit('Không gửi khi tải lịch sử'), false); assert.equal(requests.length, 2)
  finish(response([])); await loading
})
test('4000 UTF-16 characters and multiline text reach backend unchanged', async () => {
  const question = 'Đ\n'.repeat(2000), row = { ...answered, question }
  const chat = await loaded(method => response(method === 'POST' ? row : []))
  assert.equal(await chat.submit(question), true); assert.equal(JSON.parse(requests[1].body).message, question)
})
test('UNAVAILABLE suppresses even stray answer and citations', () => {
  const view = chatView({ ...answered, state: 'UNAVAILABLE' }); assert.equal(view.answer, ''); assert.deepEqual(view.citations, [])
})
test('missing citation fields or unknown state do not become verified answers', () => {
  for (const row of [{ ...answered, citations: [] }, { ...answered, citations: [{ doc_id: 'fixture-doc' }] }, { ...answered, state: 'UNKNOWN' }]) {
    const view = chatView(row); assert.equal(view.answer, ''); assert.deepEqual(view.citations, []); assert.notEqual(view.status, 'Đã trả lời')
  }
  assert.match(chatView({ ...unavailable, state: 'PROCESSING' }).status, /Đang xử lý/)
})
test('invalid history body fails closed without showing backend content', async () => {
  const chat = await loaded(() => response({ answer: 'not a history list' })); assert.deepEqual(chat.getSnapshot().rows, []); assert.ok(chat.getSnapshot().error)
})
test('invalid POST body does not clear draft or become a successful answer', async () => {
  const chat = await loaded(method => response(method === 'POST' ? { answer: 'not a chat record' } : []))
  assert.equal(await chat.submit(answered.question), false); assert.deepEqual(chat.getSnapshot().rows, []); assert.equal(chat.getSnapshot().observed, 'error')
})

for (const [status, expected] of [[403, /không có quyền/], [422, /không hợp lệ/]]) {
  test(`POST ${status} remains an error without exposing reflected credentials or retrying`, async () => {
    const chat = await loaded(method => response(method === 'POST' ? { message: 'KAG-secret-fixture /private/credentials' } : [], method === 'POST' ? status : 200))
    assert.equal(await chat.submit(answered.question), false); assert.equal(requests.length, 2)
    assert.deepEqual(chat.getSnapshot().rows, []); assert.equal(chat.getSnapshot().observed, 'error')
    assert.match(chat.getSnapshot().requestError, expected); assert.doesNotMatch(chat.getSnapshot().requestError, /KAG-secret-fixture|private/)
    assert.equal(tokens.has(tokenKey), true)
  })
}
test('GET 401 clears the session without inferring KAG readiness', async () => {
  const chat = await loaded(() => new Response('Unauthorized', { status: 401 }))
  assert.equal(expired, true); assert.equal(tokens.has(tokenKey), false)
  assert.deepEqual(chat.getSnapshot().rows, []); assert.match(chat.getSnapshot().error, /đăng nhập/)
  assert.equal(chat.getSnapshot().observed, 'idle')
})
test('HTTP success with UNAVAILABLE does not promote it to ANSWERED or show stray citations', async () => {
  const row = { ...answered, state: 'UNAVAILABLE' }
  const chat = await loaded(method => response(method === 'POST' ? row : []))
  assert.equal(await chat.submit(answered.question), true); assert.equal(requests.length, 2)
  assert.equal(chat.getSnapshot().observed, 'unavailable'); assert.equal(chat.getSnapshot().rows[0].state, 'UNAVAILABLE')
  assert.equal(chatView(row).answer, ''); assert.deepEqual(chatView(row).citations, [])
})
