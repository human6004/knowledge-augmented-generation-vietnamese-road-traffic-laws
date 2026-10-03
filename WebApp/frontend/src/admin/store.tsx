import { createContext, useCallback, useContext, useRef, useState } from 'react'
import type { SignRecord } from './import-data'

/* ---------- Types ---------- */
export type DocStatus = 'Chờ xử lý' | 'Đang xử lý' | 'Chờ duyệt' | 'Đã lập chỉ mục' | 'Lưu trữ' | 'Lỗi'
export interface LegalDoc {
  id: string
  name: string
  type: 'Luật' | 'Nghị định' | 'Thông tư' | 'Quyết định'
  effective: string
  status: DocStatus
  chunks: number
  entities: number
  step: number // 0..5 pipeline progress
  updated: string
}

export type JobStatus = 'queued' | 'running' | 'success' | 'failed' | 'cancelled'
export interface Job {
  id: string
  taskId: string
  title: string
  command: string
  status: JobStatus
  progress: number
  logs: string[]
  startedAt: string
  duration?: number
}

export interface QBankItem {
  id: string
  chapter: string
  question: string
  options: string[]
  answer: number
  critical: boolean
  explanation: string
  source: string
}

export interface ChatLog {
  id: string
  user: string
  question: string
  answer: string
  latency: number
  feedback: 'up' | 'down' | null
  status: 'Đã trả lời' | 'Không có căn cứ' | 'Phản hồi sai' | 'Văn bản hết hiệu lực'
  resolved: boolean
  time: string
}

export interface AppUser {
  id: string
  name: string
  email: string
  role: 'Người học' | 'Biên tập viên' | 'Quản trị viên'
  licenseClass: string
  questions: number
  active: boolean
  joined: string
}

export interface KagConfig {
  bizScene: 'legal' | 'default'
  language: 'vi' | 'en'
  hostAddr: string
  openieModel: string
  chatModel: string
  vectorModel: string
  baseUrl: string
  apiKey: string
  chainNum: number
  threadNum: number
  splitLength: number
  splitOverlap: number
  similarityThreshold: number | null
  evalThreads: number
  evalUpperLimit: number
  topK: number
  kgCsThreshold: number
  kgFrTopK: number
  kgFrThreshold: number
  rcTopK: number
  rcScoreThreshold: number
  enableRef: boolean
  solverVariant: 'baseline' | 'evidence_aware'
}

/* ---------- Task catalog (UI replacements for CLI commands) ---------- */
export interface TaskDef {
  id: string
  group: 'Hạ tầng' | 'Dự án' | 'Nạp dữ liệu' | 'Đánh giá' | 'Kiểm tra'
  title: string
  desc: string
  command: string
  steps: string[]
}

export const tasks: TaskDef[] = [
  {
    id: 'infra-up', group: 'Hạ tầng', title: 'Khởi động dịch vụ OpenSPG',
    desc: 'Bật neo4j, mysql, minio và openspg-server.',
    command: 'docker compose -f deploy/docker-compose.yml up -d',
    steps: ['Pull image release-openspg-*', 'Khởi động release-openspg-mysql', 'Khởi động release-openspg-neo4j', 'Khởi động release-openspg-minio', 'Khởi động release-openspg-server', 'Healthcheck http://127.0.0.1:8887 → 200 OK'],
  },
  {
    id: 'docker-build', group: 'Hạ tầng', title: 'Build image riêng',
    desc: 'Build kag-legal-* từ deploy/ (không phụ thuộc compose gốc).',
    command: 'deploy/build.sh',
    steps: ['Đọc deploy/.env', 'Build kag-legal-mysql (FROM openspg-mysql)', 'Build kag-legal-neo4j + restore-entrypoint', 'Build kag-legal-minio', 'Build kag-legal-server + start.sh', 'Build kag-legal-app (python:3.10-slim)', 'Build kag-legal-web (node → nginx)', 'Gắn tag ${TAG} ✓'],
  },
  {
    id: 'docker-pack', group: 'Hạ tầng', title: 'Đóng gói để chia sẻ',
    desc: 'docker save toàn bộ image + compose + dump thành một tệp.',
    command: 'deploy/pack.sh',
    steps: ['docker compose config --images', 'docker save | gzip → images/kag-legal.tar.gz', 'Chép docker-compose.yml, env.example, install.sh/.ps1', 'Kèm dumps/legal.dump', 'Bỏ khối build: khỏi compose', 'Sinh SHA256SUMS', 'Ghi dist/kag-legal-bundle.tar.gz ✓'],
  },
  {
    id: 'infra-check', group: 'Hạ tầng', title: 'Kiểm tra container',
    desc: 'Liệt kê trạng thái container và volume.',
    command: 'docker ps -a && docker compose config --volumes',
    steps: ['release-openspg-server   Up 3 hours', 'release-openspg-neo4j    Up 3 hours', 'release-openspg-mysql    Up 3 hours', 'release-openspg-minio    Up 3 hours', 'Volumes: neo4j-data, mysql-data, minio-data'],
  },
  {
    id: 'project-restore', group: 'Dự án', title: 'Đăng ký dự án KAG',
    desc: 'Khôi phục project legal lên OpenSPG server.',
    command: 'knext project restore --host_addr http://127.0.0.1:8887 --proj_path .',
    steps: ['Đọc kag_config.yaml (UTF-8)', 'Kết nối host_addr', 'Tạo namespace Legal', 'Ghi project_id vào cấu hình'],
  },
  {
    id: 'schema-commit', group: 'Dự án', title: 'Commit schema',
    desc: 'Đẩy schema Điều/Khoản/Điểm, Hành vi, Chế tài.',
    command: 'knext schema commit',
    steps: ['Phân tích Legal.schema', 'Kiểm tra check_schema.py', 'Tạo kiểu Văn bản, Điều, Khoản, Điểm', 'Tạo kiểu HànhVi, ChếTài, PhươngTiện', 'Commit thành công'],
  },
  {
    id: 'metadata', group: 'Nạp dữ liệu', title: 'Metadata → đồ thị',
    desc: 'Chuyển metadata/*.json thành nodes/edges.',
    command: 'python builder/metadata_to_graph.py',
    steps: ['Đọc metadata/*.json', 'Áp dụng PROP_MAP / REL_MAP', 'Sinh canon_id cho nút', 'Ghi data/graph/nodes.json', 'Ghi data/graph/edges.json'],
  },
  {
    id: 'inject', group: 'Nạp dữ liệu', title: 'Inject tri thức miền',
    desc: 'Nạp đồ thị ngoài qua domain_kg_inject_chain.',
    command: 'python builder/injection.py',
    steps: ['Tải nodes.json / edges.json', 'Khởi tạo domain_kg_inject_chain', 'Vector hoá thuộc tính', 'kg_writer → neo4j', 'Hoàn tất inject'],
  },
  {
    id: 'index', group: 'Nạp dữ liệu', title: 'Lập chỉ mục văn bản',
    desc: 'Chạy BuilderChainRunner trên processed/*.md.',
    command: 'python builder/indexer.py',
    steps: ['dir_file_scanner: quét thư mục', 'legal_md_reader: giữ số Khoản/Điểm', 'length_splitter (4950/100)', 'legal_schema_free_extractor', 'batch_vectorizer', 'kag_post_processor', 'kg_writer → đồ thị'],
  },
  {
    id: 'eval', group: 'Đánh giá', title: 'Chạy bộ câu hỏi kiểm thử',
    desc: 'Đánh giá hit@k trên bộ câu hỏi chuẩn.',
    command: 'python solver/eval.py',
    steps: ['Tải bộ câu hỏi', 'Khởi tạo solver pipeline', 'Truy vấn KAG (thread_num)', 'Chuẩn hoá NFC & markdown', 'Tính hit_rate / hit_all', 'Ghi runs/benchmark.txt'],
  },
  {
    id: 'benchmark', group: 'Đánh giá', title: 'So sánh KAG vs HybridRAG',
    desc: 'Benchmark ba hệ thống trên cùng tập.',
    command: 'python -m benchmark.evaluator.evaluate',
    steps: ['Load final_150_corpus_verified.json (150 câu)', 'Runner kag_runner → benchmark/runs/kag.json', 'Runner hybridrag_runner → hybridrag.json', 'Runner nativerag_runner → nativerag.json', 'citation_parser: parse citations từ answer', 'retrieval / citation / answer / grounding / abstention metrics', 'Bootstrap CI & aggregate', 'Ghi report.json'],
  },
  {
    id: 'tests', group: 'Kiểm tra', title: 'Chạy kiểm thử builder',
    desc: 'check_prompts, reader, predicate binding…',
    command: 'pytest tests/builder',
    steps: ['check_prompts.py ✓', 'test_reader_fixes.py ✓', 'test_predicate_binding.py ✓', 'test_stop_handler.py ✓', 'test_builder_fixes.py ✓'],
  },
  {
    id: 'secret', group: 'Kiểm tra', title: 'Quét lộ khoá bí mật',
    desc: 'Đảm bảo không commit API key.',
    command: 'python scripts/secret_scan.py',
    steps: ['Quét 412 tệp', 'Bỏ qua kag_config.yaml (gitignore)', 'Không phát hiện khoá lộ'],
  },
  {
    id: 'export', group: 'Kiểm tra', title: 'Xuất đồ thị',
    desc: 'Sao lưu neo4j ra dist/legal.dump.',
    command: 'docker/xuat-do-thi.ps1',
    steps: ['Dừng ghi neo4j', 'neo4j-admin database dump', 'Ghi dist/legalfinalcand.dump (1.31 GiB)', 'Sinh legalfinalcand.dump.sha256', 'Bật lại neo4j'],
  },
  {
    id: 'restore', group: 'Kiểm tra', title: 'Khôi phục đồ thị',
    desc: 'Nạp dump vào database legalfinalcand trên máy nhận.',
    command: 'docker/restore-final-graph.ps1',
    steps: ['Xác minh sha256 = 155c1e74…', 'Dừng release-openspg-neo4j', 'neo4j-admin database load legalfinalcand', 'Khởi động neo4j', 'Đếm lại: 15888 nodes / 32655 relations', 'vector_dimensions 3072 ✓'],
  },
]

/* ---------- Seed data ---------- */
const now = () => new Date().toLocaleString('vi-VN', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' })

const seedDocs: LegalDoc[] = [
  { id: 'd1', name: 'Nghị định 168/2024/NĐ-CP', type: 'Nghị định', effective: '01/01/2025', status: 'Đã lập chỉ mục', chunks: 412, entities: 2381, step: 5, updated: '28/09 14:02' },
  { id: 'd2', name: 'Luật Trật tự, an toàn giao thông đường bộ 2024', type: 'Luật', effective: '01/01/2025', status: 'Đã lập chỉ mục', chunks: 296, entities: 1740, step: 5, updated: '27/09 09:15' },
  { id: 'd3', name: 'Thông tư 35/2024/TT-BGTVT (sát hạch GPLX)', type: 'Thông tư', effective: '01/01/2025', status: 'Chờ duyệt', chunks: 188, entities: 902, step: 3, updated: '30/09 16:40' },
  { id: 'd4', name: 'Nghị định 100/2019/NĐ-CP', type: 'Nghị định', effective: 'Hết hiệu lực', status: 'Lưu trữ', chunks: 350, entities: 2011, step: 5, updated: '02/01 08:00' },
]

const seedQ: QBankItem[] = [
  { id: 'q1', chapter: 'Khái niệm và quy tắc', question: 'Phần đường xe chạy là gì?', options: ['Phần của đường bộ dùng cho phương tiện qua lại', 'Phần đường dành cho người đi bộ', 'Dải phân cách'], answer: 0, critical: false, explanation: 'Theo khoản 2 Điều 2 Luật TTATGT.', source: 'Luật TTATGT 2024' },
  { id: 'q2', chapter: 'Khái niệm và quy tắc', question: 'Người lái xe có nồng độ cồn trong máu có được điều khiển xe không?', options: ['Được nếu dưới mức cho phép', 'Nghiêm cấm', 'Chỉ cấm ô tô'], answer: 1, critical: true, explanation: 'Câu điểm liệt — nghiêm cấm tuyệt đối.', source: 'Luật TTATGT 2024' },
  { id: 'q3', chapter: 'Biển báo đường bộ', question: 'Biển P.102 có ý nghĩa gì?', options: ['Cấm đi ngược chiều', 'Cấm dừng xe', 'Đường một chiều'], answer: 0, critical: false, explanation: 'Biển cấm hình tròn nền đỏ vạch trắng.', source: 'QCVN 41:2024' },
  { id: 'q4', chapter: 'Sa hình', question: 'Xe nào được đi trước trong tình huống giao nhau không có đèn?', options: ['Xe bên phải không vướng', 'Xe con', 'Xe tải'], answer: 0, critical: false, explanation: 'Nhường đường cho xe đi đến từ bên phải.', source: 'Luật TTATGT 2024' },
  { id: 'q5', chapter: 'Văn hoá giao thông', question: 'Khi gặp tai nạn, người lái xe liên quan phải làm gì?', options: ['Bỏ đi', 'Dừng xe, giữ nguyên hiện trường, cấp cứu', 'Chụp ảnh'], answer: 1, critical: true, explanation: 'Nghĩa vụ khi xảy ra tai nạn.', source: 'Luật TTATGT 2024' },
]

const seedLogs: ChatLog[] = [
  { id: 'c1', user: 'nguyen.an', question: 'Xe máy vượt đèn đỏ bị phạt bao nhiêu?', answer: 'Phạt 4–6 triệu đồng, trừ 4 điểm GPLX…', latency: 2.1, feedback: 'up', status: 'Đã trả lời', resolved: true, time: '01/10 09:12' },
  { id: 'c2', user: 'tran.binh', question: 'Đi xe đạp điện không đội mũ có bị phạt không?', answer: 'Không tìm thấy căn cứ phù hợp.', latency: 3.4, feedback: 'down', status: 'Không có căn cứ', resolved: false, time: '01/10 08:47' },
  { id: 'c3', user: 'le.chi', question: 'Ô tô chạy quá tốc độ 15km/h phạt bao nhiêu?', answer: 'Theo NĐ 100/2019, phạt 2–3 triệu…', latency: 2.7, feedback: 'down', status: 'Văn bản hết hiệu lực', resolved: false, time: '30/09 21:05' },
  { id: 'c4', user: 'pham.dung', question: 'Biển P.127 là gì?', answer: 'Biển hạn chế tốc độ tối đa cho phép theo xe hạng B.', latency: 1.8, feedback: 'down', status: 'Phản hồi sai', resolved: false, time: '30/09 18:33' },
  { id: 'c5', user: 'nguyen.an', question: 'Thủ tục đổi bằng lái hạng B?', answer: 'Chuẩn bị hồ sơ gồm đơn đề nghị…', latency: 2.4, feedback: null, status: 'Đã trả lời', resolved: true, time: '30/09 15:20' },
  { id: 'c6', user: 'vo.em', question: 'Trừ điểm GPLX được phục hồi khi nào?', answer: 'Sau 12 tháng không bị trừ điểm…', latency: 2.0, feedback: 'up', status: 'Đã trả lời', resolved: true, time: '29/09 10:02' },
]

const seedUsers: AppUser[] = [
  { id: 'u1', name: 'Nguyễn An', email: 'an@luatgt.vn', role: 'Quản trị viên', licenseClass: 'B', questions: 128, active: true, joined: '12/03/2026' },
  { id: 'u2', name: 'Trần Bình', email: 'binh@gmail.com', role: 'Người học', licenseClass: 'A1', questions: 42, active: true, joined: '02/06/2026' },
  { id: 'u3', name: 'Lê Chi', email: 'chi@gmail.com', role: 'Biên tập viên', licenseClass: 'B', questions: 77, active: true, joined: '18/07/2026' },
  { id: 'u4', name: 'Phạm Dũng', email: 'dung@yahoo.com', role: 'Người học', licenseClass: 'C1', questions: 9, active: false, joined: '20/08/2026' },
  { id: 'u5', name: 'Võ Em', email: 'em@gmail.com', role: 'Người học', licenseClass: 'B', questions: 31, active: true, joined: '05/09/2026' },
]

export const defaultConfig: KagConfig = {
  bizScene: 'legal', language: 'vi', hostAddr: 'http://127.0.0.1:8887',
  openieModel: 'qwen2.5-72b-instruct', chatModel: 'qwen2.5-72b-instruct', vectorModel: 'bge-m3',
  baseUrl: 'https://api.example.com/v1', apiKey: '',
  chainNum: 2, threadNum: 2, splitLength: 4950, splitOverlap: 100, similarityThreshold: null,
  evalThreads: 8, evalUpperLimit: 150, topK: 20,
  kgCsThreshold: 0.9, kgFrTopK: 20, kgFrThreshold: 0.8, rcTopK: 20, rcScoreThreshold: 0.65, enableRef: true, solverVariant: 'baseline',
}

/* ---------- Store ---------- */
interface Store {
  docs: LegalDoc[]
  setDocs: React.Dispatch<React.SetStateAction<LegalDoc[]>>
  jobs: Job[]
  runTask: (taskId: string, opts?: { label?: string; onDone?: () => void }) => string
  cancelJob: (id: string) => void
  qbank: QBankItem[]
  signs: SignRecord[]
  setSigns: React.Dispatch<React.SetStateAction<SignRecord[]>>
  setQbank: React.Dispatch<React.SetStateAction<QBankItem[]>>
  logs: ChatLog[]
  setLogs: React.Dispatch<React.SetStateAction<ChatLog[]>>
  users: AppUser[]
  setUsers: React.Dispatch<React.SetStateAction<AppUser[]>>
  config: KagConfig
  setConfig: React.Dispatch<React.SetStateAction<KagConfig>>
  lastEval: { hit: number; total: number; time: string } | null
  toast: string | null
  notify: (msg: string) => void
}

const Ctx = createContext<Store | null>(null)

export function AdminProvider({ children }: { children: React.ReactNode }) {
  const [docs, setDocs] = useState(seedDocs)
  const [jobs, setJobs] = useState<Job[]>([
    { id: 'j0', taskId: 'eval', title: 'Chạy bộ câu hỏi kiểm thử', command: 'python solver/eval.py', status: 'success', progress: 100, logs: ['hit@20 = 0.861 (143/166)'], startedAt: '29/09 22:10', duration: 412 },
  ])
  const [qbank, setQbank] = useState(seedQ)
  const [signs, setSigns] = useState<SignRecord[]>([])
  const [logs, setLogs] = useState(seedLogs)
  const [users, setUsers] = useState(seedUsers)
  const [config, setConfig] = useState(defaultConfig)
  const [lastEval, setLastEval] = useState<Store['lastEval']>({ hit: 0.861, total: 166, time: '29/09 22:10' })
  const [toast, setToast] = useState<string | null>(null)
  const timers = useRef<Record<string, number>>({})
  const toastTimer = useRef<number | undefined>(undefined)

  const notify = useCallback((msg: string) => {
    setToast(msg)
    window.clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => setToast(null), 2600)
  }, [])

  const runTask: Store['runTask'] = useCallback((taskId, opts) => {
    const def = tasks.find((t) => t.id === taskId)!
    const id = 'j' + Date.now()
    const start = Date.now()
    const command = opts?.label ? `${def.command} ${opts.label}` : def.command
    setJobs((js) => [{ id, taskId, title: def.title, command, status: 'running', progress: 0, logs: [`$ ${command}`], startedAt: now() }, ...js])
    let i = 0
    timers.current[id] = window.setInterval(() => {
      const line = def.steps[i]
      i++
      const done = i >= def.steps.length
      setJobs((js) =>
        js.map((j) => {
          if (j.id !== id || j.status !== 'running') return j
          const ts = new Date().toLocaleTimeString('vi-VN')
          const extra = done && taskId === 'eval' ? [`[${ts}] hit@${config.topK} = 0.874 (145/166)`] : []
          return {
            ...j,
            progress: Math.round((i / def.steps.length) * 100),
            logs: [...j.logs, `[${ts}] ${line}`, ...extra, ...(done ? [`✓ Hoàn tất trong ${Math.round((Date.now() - start) / 1000)}s`] : [])],
            status: done ? 'success' : 'running',
            duration: done ? Math.round((Date.now() - start) / 1000) : undefined,
          }
        })
      )
      if (done) {
        window.clearInterval(timers.current[id])
        if (taskId === 'eval') setLastEval({ hit: 0.874, total: 166, time: now() })
        opts?.onDone?.()
      }
    }, 700)
    return id
  }, [config.topK])

  const cancelJob = useCallback((id: string) => {
    window.clearInterval(timers.current[id])
    setJobs((js) => js.map((j) => (j.id === id && j.status === 'running' ? { ...j, status: 'cancelled', logs: [...j.logs, '✗ Đã huỷ bởi quản trị viên'] } : j)))
  }, [])

  return (
    <Ctx.Provider value={{ docs, setDocs, jobs, runTask, cancelJob, qbank, setQbank, signs, setSigns, logs, setLogs, users, setUsers, config, setConfig, lastEval, toast, notify }}>
      {children}
    </Ctx.Provider>
  )
}

export function useAdmin() {
  const c = useContext(Ctx)
  if (!c) throw new Error('useAdmin outside AdminProvider')
  return c
}
