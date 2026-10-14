import { useState } from 'react'
import { tasks, useAdmin, type JobStatus } from '../admin/store'
import { Badge, Button, Card, Page, Progress, Terminal, inputCls, type Tone } from '../admin/ui'

const groups = ['Hạ tầng', 'Dự án', 'Nạp dữ liệu', 'Đánh giá', 'Kiểm tra'] as const
export const jobTone: Record<JobStatus, [Tone, string]> = {
  queued: ['gray', 'Chờ'],
  running: ['gold', 'Đang chạy'],
  success: ['green', 'Thành công'],
  failed: ['red', 'Lỗi'],
  cancelled: ['gray', 'Đã huỷ'],
}

export default function AdminPipeline() {
  const { jobs, runTask, cancelJob, config, notify } = useAdmin()
  const [selected, setSelected] = useState<string | null>(jobs[0]?.id ?? null)
  const [indexDir, setIndexDir] = useState('../data/processed')
  const job = jobs.find((j) => j.id === selected)
  const runningIds = new Set(jobs.filter((j) => j.status === 'running').map((j) => j.taskId))

  function run(taskId: string) {
    const label = taskId === 'index' ? indexDir : taskId === 'eval' ? `--thread_num ${config.evalThreads} --upper_limit ${config.evalUpperLimit}` : undefined
    const id = runTask(taskId, { label, onDone: () => notify('Tác vụ đã hoàn tất') })
    setSelected(id)
  }

  function runAll() {
    const order = ['metadata', 'inject', 'index', 'eval']
    let k = 0
    const next = () => {
      const t = order[k++]
      if (!t) return notify('Đã chạy xong toàn bộ pipeline nạp dữ liệu')
      setSelected(runTask(t, { label: t === 'index' ? indexDir : undefined, onDone: next }))
    }
    next()
  }

  return (
    <Page
      title="Pipeline & tác vụ"
      subtitle="Chạy các bước KAG bằng giao diện thay cho dòng lệnh — log được hiển thị trực tiếp."
      actions={<Button variant="dark" onClick={runAll}>▶ Chạy toàn bộ pipeline nạp</Button>}
    >
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="space-y-5">
          {groups.map((g) => (
            <div key={g}>
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted">{g}</p>
              <div className="grid gap-3 sm:grid-cols-2">
                {tasks.filter((t) => t.group === g).map((t) => {
                  const running = runningIds.has(t.id)
                  const last = jobs.find((j) => j.taskId === t.id)
                  return (
                    <Card key={t.id} className="p-4 flex flex-col">
                      <div className="flex items-start justify-between gap-2">
                        <h3 className="text-[14px] font-semibold text-navy">{t.title}</h3>
                        {last && <Badge tone={jobTone[last.status][0]}>{jobTone[last.status][1]}</Badge>}
                      </div>
                      <p className="mt-1 text-[12.5px] text-muted">{t.desc}</p>
                      <code className="mt-3 block truncate rounded-lg bg-sidebar border border-line px-2.5 py-1.5 font-mono text-[11px] text-text-secondary" title={t.command}>
                        $ {t.command}
                      </code>
                      {t.id === 'index' && (
                        <select value={indexDir} onChange={(e) => setIndexDir(e.target.value)} className={`${inputCls} mt-2 py-1.5 text-xs`} aria-label="Thư mục lập chỉ mục">
                          <option value="../data/processed">Toàn bộ corpus (data/processed)</option>
                          <option value="../data/trial">Tập thử (data/trial)</option>
                          <option value="../data/new">Văn bản mới (data/new)</option>
                        </select>
                      )}
                      <div className="mt-3 flex items-center gap-2 pt-1 mt-auto">
                        <Button size="sm" variant={running ? 'outline' : 'primary'} disabled={running} onClick={() => run(t.id)}>
                          {running ? 'Đang chạy…' : '▶ Chạy'}
                        </Button>
                        {last && (
                          <button onClick={() => setSelected(last.id)} className="text-xs text-muted hover:text-navy">Xem log</button>
                        )}
                      </div>
                    </Card>
                  )
                })}
              </div>
            </div>
          ))}
        </div>

        <div className="space-y-5 xl:sticky xl:top-6 self-start">
          <Card title="Log tác vụ" right={job?.status === 'running' && <Button size="sm" variant="danger" onClick={() => cancelJob(job.id)}>Huỷ</Button>}>
            <div className="px-5 pb-5">
              {job ? (
                <>
                  <div className="flex items-center justify-between mb-2 text-[13px]">
                    <span className="font-medium text-navy">{job.title}</span>
                    <span className="text-muted">{job.progress}%</span>
                  </div>
                  <Progress value={job.progress} tone={job.status === 'success' ? 'green' : job.status === 'cancelled' ? 'red' : 'accent'} />
                  <Terminal lines={job.logs} className="mt-3 h-72" />
                </>
              ) : (
                <p className="text-sm text-muted">Chọn một tác vụ để xem log.</p>
              )}
            </div>
          </Card>

          <Card title="Lịch sử chạy">
            <ul className="px-2 pb-3 max-h-80 overflow-y-auto">
              {jobs.map((j) => (
                <li key={j.id}>
                  <button
                    onClick={() => setSelected(j.id)}
                    className={`w-full flex items-center justify-between gap-3 rounded-xl px-3 py-2 text-left transition-colors ${j.id === selected ? 'bg-selected' : 'hover:bg-selected/60'}`}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-[13px] font-medium text-navy">{j.title}</span>
                      <span className="block text-[11.5px] text-muted">{j.startedAt}{j.duration ? ` · ${j.duration}s` : ''}</span>
                    </span>
                    <Badge tone={jobTone[j.status][0]}>{jobTone[j.status][1]}</Badge>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </Page>
  )
}
