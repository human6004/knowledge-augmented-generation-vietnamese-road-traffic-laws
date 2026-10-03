import assert from 'node:assert/strict'
import { api, send, tokenKey } from '../src/api.ts'
import { normalizeImport } from '../src/pages/server/import-normalization.ts'

const values = new Map([[tokenKey, 'test-token']])
globalThis.sessionStorage = { getItem: key => values.get(key), removeItem: key => values.delete(key) }
let expired = false
globalThis.window = { dispatchEvent: event => { expired = event.type === 'luatgt-session-expired' } }
globalThis.fetch = async (url, options) => {
  assert.equal(url, '/api/auth/me')
  assert.equal(options.headers.get('Authorization'), 'Bearer test-token')
  return new Response(JSON.stringify({ role: 'USER' }))
}
assert.deepEqual(await api('/auth/me'), { role: 'USER' })
globalThis.fetch = async () => new Response(JSON.stringify({ message: 'Phiên đã hết hạn' }), { status: 401 })
await assert.rejects(api('/questions'), /Phiên đã hết hạn/)
assert.equal(expired, true)
assert.equal(values.has(tokenKey), false)
globalThis.fetch = async () => { throw new Error('offline') }
await assert.rejects(api('/questions'), /Không kết nối được backend/)
assert.equal(send('POST', { selected: 0 }).body, '{"selected":0}')
const csv = normalizeImport('questions', { id: 'Q1', question: 'Câu?', chapter: '5', option1: 'A', option2: 'B', answer: '2', critical: 'false' })
assert.equal(csv.externalId, 'Q1')
assert.deepEqual(csv.options, ['A','B'])
assert.equal(csv.correctAnswer, 1)
assert.equal(csv.chapter, 5)
assert.equal(csv.critical, false)
assert.equal(normalizeImport('questions', { options: ['A','B'], answer: 0 }).correctAnswer, 0)
assert.equal(normalizeImport('signs', { sign_id: 'QCVN::P.1' }).externalId, 'QCVN::P.1')
console.log('PASS: real API session/errors and import normalization')
