import { useState, useEffect, useRef } from 'react'
import { Page,Button } from '../../admin/ui'
import { useData,Notice,inputClass } from './shared'
import { loadKagStatus, loadSampleInspection, runRetrieval, inspectionError, type KagStatus, type Retrieval, type SampleInspection } from './kag-inspection'
export function Infrastructure() {
  const data=useData<Record<string,string>>('/admin/infrastructure'), [kag,setKag]=useState<KagStatus>(), [statusError,setStatusError]=useState(''), [statusBusy,setStatusBusy]=useState(true)
  const [message,setMessage]=useState(''), [topK,setTopK]=useState(3), [expand,setExpand]=useState(false), [result,setResult]=useState<Retrieval>(), [retrieveError,setRetrieveError]=useState(''), [busy,setBusy]=useState(false), pending=useRef(false)
  const [elapsedMs,setElapsedMs]=useState<number>()
  const [sample,setSample]=useState<SampleInspection>(), [sampleError,setSampleError]=useState('')
  async function refreshStatus(signal?:AbortSignal) {
    setStatusBusy(true); setStatusError(''); setKag(undefined); setSample(undefined); setSampleError('')
    try { const value=await loadKagStatus(signal); if(!signal?.aborted)setKag(value) }
    catch(error) { if(!signal?.aborted)setStatusError(inspectionError(error)) }
    try { const value=await loadSampleInspection(signal); if(!signal?.aborted)setSample(value) }
    catch(error) { if(!signal?.aborted)setSampleError(inspectionError(error)) }
    finally { if(!signal?.aborted)setStatusBusy(false) }
  }
  useEffect(()=>{const controller=new AbortController();void refreshStatus(controller.signal);return()=>controller.abort()},[])
  function refresh(){data.reload();void refreshStatus()}
  const labels={liveness:'KAG API liveness',queryReadiness:'Query readiness',retrievalReadiness:'Retrieval readiness',vectorRetrievalReadiness:'Vector retrieval readiness',release:'Verified release artifact'}
  return <Page title="Hạ tầng" subtitle="Liveness chỉ chứng minh API phản hồi. Readiness và release được kiểm tra riêng qua backend." actions={<Button disabled={data.loading||statusBusy||busy} onClick={refresh}>Kiểm tra lại</Button>}>
    <h2 className="font-semibold">Dịch vụ WebApp</h2><Notice {...data} retry={data.reload}/>
    {Object.entries(data.value||{}).map(([name,state])=><div key={name} className="flex justify-between border-b border-line py-4"><p>{name}</p><p className={state==='UP'?'text-emerald-700':'text-red-700'}>{state==='UP'?'Kết nối được':'Chưa khả dụng'}</p></div>)}
    <h2 className="font-semibold mt-8">KAG HTTP API</h2><Notice loading={statusBusy} error={statusError} retry={()=>void refreshStatus()}/>
    {kag&&Object.entries(labels).map(([key,label])=>{const check=kag[key as keyof KagStatus];return <section key={key} className="border-b border-line py-4"><div className="flex flex-wrap justify-between gap-3"><h3>{label}</h3><p className={check.state==='ALIVE'||check.state==='READY'?'text-emerald-700':'text-amber-800'}>{check.state}{check.httpStatus?` · HTTP ${check.httpStatus}`:''}{check.code?` · ${check.code}`:''}</p></div>{check.evidence&&<pre className="mt-3 text-xs whitespace-pre-wrap break-words max-w-full">{JSON.stringify(check.evidence,null,2)}</pre>}</section>})}
    <p className="text-sm text-muted mt-4">Release artifact có thể tồn tại khi graph chưa sẵn sàng. Không có verified release thì truy xuất chưa khả dụng.</p>
    <h2 className="font-semibold mt-8">Kiểm thử Retrieval</h2>
    <p className="text-sm mt-3">Câu tiếng Việt được embedding rồi tìm vector; expand thêm graph context. Không chạy Solver hoặc full legal answering.</p>
    <Notice error={sampleError}/>
    <form className="mt-4 space-y-4" onSubmit={async e=>{e.preventDefault();if(pending.current)return;pending.current=true;setBusy(true);setResult(undefined);setRetrieveError('');setElapsedMs(undefined);const started=performance.now();try{setResult(await runRetrieval(message,topK,expand))}catch(error){setRetrieveError(inspectionError(error))}finally{setElapsedMs(performance.now()-started);pending.current=false;setBusy(false)}}}>
      <label className="block text-sm">Nội dung truy xuất<textarea required maxLength={4000} rows={3} disabled={busy} value={message} onChange={e=>setMessage(e.target.value)} className={`${inputClass} mt-2`}/></label>
      <div className="flex flex-wrap items-end gap-4"><label className="text-sm">Số kết quả (1–10)<input required type="number" min={1} max={10} step={1} disabled={busy} value={topK} onChange={e=>setTopK(Number(e.target.value))} className={`${inputClass} mt-2`}/></label><label className="text-sm"><input type="checkbox" disabled={busy} checked={expand} onChange={e=>setExpand(e.target.checked)}/> Mở rộng graph context</label><Button type="submit" disabled={busy||!message.trim()||topK<1||topK>10}>{busy?'Đang truy xuất…':'Chạy thử truy xuất'}</Button></div>
    </form>
    <Notice loading={busy} error={retrieveError}/>
    {elapsedMs!==undefined&&<p className="mt-3 text-sm text-muted">Thời gian request qua backend: {elapsedMs.toFixed(1)} ms; không phải thời gian riêng của Neo4j.</p>}
    {result&&<section className="mt-5 min-w-0" aria-live="polite"><p className="text-sm break-words">{result.items.length} kết quả · request {result.request_id} · release {result.release_id} · snapshot {result.source_snapshot_id}</p>{!result.items.length&&<p>Không tìm được evidence; không có kết luận pháp luật.</p>}{result.items.map((item,i)=>{
      const node=sample?.release_id===result.release_id&&sample.source_snapshot_id===result.source_snapshot_id?sample.nodes.find(n=>n.entity_type===item.entity_type&&n.entity_id===item.entity_id):undefined
      const doc=sample?.nodes.find(n=>n.entity_type==='VietRoadTraffic.LegalDocument'&&n.entity_id===item.doc_id)
      return <article key={i} className="py-4 border-b border-line text-sm space-y-2 min-w-0"><h3 className="font-semibold break-words">{item.entity_type} · {item.entity_id}</h3><p>Score: {item.score??'Không có'} · {item.vector_sources.length} vector source</p><p className="break-words">Văn bản: {item.doc_id??'Không có'}{doc?` · ${String(doc.properties.title??'')}`:''} · Unit: {item.unit_id??'Không có'} · Sign: {item.sign_id??'Không có'}</p>{Object.entries(item.source_texts).map(([field,text])=><details key={field}><summary className="cursor-pointer underline">Nội dung nguồn: {field}</summary><blockquote className="mt-2 whitespace-pre-wrap break-words border-l border-line pl-3">{text??'Không có'}</blockquote></details>)}{node?node.sources.map(s=><p key={s.evidence_id} className="text-xs break-all">Evidence {s.field}: {s.evidence_id} · source SHA-256 {s.source_sha256}</p>):<p>Evidence hash chưa đối chiếu được với source catalog của cùng release.</p>}<details><summary className="cursor-pointer underline">Relation context và vector provenance ({item.graph_context.length})</summary><pre className="mt-2 text-xs whitespace-pre-wrap break-words">{JSON.stringify({vector_sources:item.vector_sources,graph_context:item.graph_context},null,2)}</pre></details></article>
    })}</section>}
  </Page>
}
