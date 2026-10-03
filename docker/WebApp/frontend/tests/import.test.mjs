import assert from 'node:assert/strict'
import { parseCsv, tableObjects, validateRows, samples, mergeRecords } from '../src/admin/import-data.ts'

assert.deepEqual(parseCsv('\uFEFFa,b\r\n"x,y","line\n""quote"""'), [['a','b'], ['x,y','line\n"quote"']])
assert.throws(() => parseCsv('a\n"open'))
assert.throws(() => parseCsv('a\n"closed"bad'))
assert.throws(() => tableObjects([['a','a'], ['1','2']]))
for (const kind of ['signs','questions','documents']) assert.equal(validateRows(kind, tableObjects(parseCsv(samples[kind])))[0].errors.length, 0)
const sign = {code:'p.1', name:'Mẫu', group:'Cấm', meaning:'Nội dung', source:'Nguồn'}
assert.equal(validateRows('signs', [sign, {...sign, code:'P.1'}])[1].errors[0], 'Trùng mã trong tệp')
assert.ok(validateRows('signs', [{...sign, source:''}])[0].errors.length)
assert.ok(validateRows('questions', [{id:'q',chapter:'Chương',question:'Câu?',options:['A','B'],answer:2,critical:false,source:'Nguồn'}])[0].errors.length)
assert.ok(validateRows('questions', [{id:'q',chapter:'Chương',question:'Câu?',option1:'A',option2:'',option3:'C',answer:2,critical:false,source:'Nguồn'}])[0].errors.length)
assert.equal(validateRows('questions', [{id:'q',chapter:'Chương',question:'Câu?',options:['A','B'],answer:0,critical:false,source:'Nguồn'}])[0].record.answer, 0)
assert.ok(validateRows('documents', [{id:'d', name:'Mẫu', type:'Luật', effective:'2025-02-30'}])[0].errors.length)
assert.throws(() => validateRows('signs', {}))
assert.equal(mergeRecords([sign], [{...sign,name:'Mới'}], (s) => s.code, false)[0].name, 'Mẫu')
assert.equal(mergeRecords([sign], [{...sign,name:'Mới'}], (s) => s.code, true)[0].name, 'Mới')
console.log('Import parsing, validation and duplicate checks passed')
