import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import UserLayout from './layouts/UserLayout'
import AdminLayout from './layouts/AdminLayout'
import ChatPage from './pages/ChatPage'
import ExamPage from './pages/ExamPage'
import PenaltySearchPage from './pages/PenaltySearchPage'
import SignLibraryPage from './pages/SignLibraryPage'
import ChapterStudyPage from './pages/ChapterStudyPage'
import AdminDashboard from './pages/AdminDashboard'
import AdminKnowledge from './pages/AdminKnowledge'
import AdminPipeline from './pages/AdminPipeline'
import AdminGraph from './pages/AdminGraph'
import AdminBenchmark from './pages/AdminBenchmark'
import AdminQuestions from './pages/AdminQuestions'
import AdminChatLogs from './pages/AdminChatLogs'
import AdminUsers from './pages/AdminUsers'
import AdminConfig from './pages/AdminConfig'
import AdminDocker from './pages/AdminDocker'

function ModeBar() {
  const loc = useLocation()
  const nav = useNavigate()
  const isAdmin = loc.pathname.startsWith('/admin')
  return (
    <div
      className="fixed bottom-4 right-16 z-50 flex items-center gap-0.5 rounded-full p-1 shadow-[0_6px_20px_-6px_rgba(53,45,36,0.45)] ring-1 ring-black/5"
      style={{ background: 'var(--color-navy)' }}
    >
      <button
        onClick={() => nav('/chat')}
        className={`px-3.5 py-1.5 rounded-full text-xs font-semibold whitespace-nowrap transition-colors ${!isAdmin ? 'text-navy shadow-xs' : 'text-line hover:text-white'}`}
        style={!isAdmin ? { background: 'var(--color-accent)' } : {}}
      >
        Người dùng
      </button>
      <button
        onClick={() => nav('/admin/dashboard')}
        className={`px-3.5 py-1.5 rounded-full text-xs font-semibold whitespace-nowrap transition-colors ${isAdmin ? 'text-navy shadow-xs' : 'text-line hover:text-white'}`}
        style={isAdmin ? { background: 'var(--color-accent)' } : {}}
      >
        Quản trị
      </button>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <ModeBar />
      <Routes>
        <Route path="/" element={<Navigate to="/chat" replace />} />
        <Route element={<UserLayout />}>
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/tra-cuu" element={<PenaltySearchPage />} />
          <Route path="/bien-bao" element={<SignLibraryPage />} />
          <Route path="/on-thi" element={<ChapterStudyPage />} />
          <Route path="/tien-do" element={<Navigate to="/on-thi" replace />} />
          <Route path="/exam" element={<ExamPage />} />
        </Route>
        <Route path="/admin" element={<Navigate to="/admin/dashboard" replace />} />
        <Route element={<AdminLayout />}>
          <Route path="/admin/dashboard" element={<AdminDashboard />} />
          <Route path="/admin/knowledge" element={<AdminKnowledge />} />
          <Route path="/admin/pipeline" element={<AdminPipeline />} />
          <Route path="/admin/graph" element={<AdminGraph />} />
          <Route path="/admin/benchmark" element={<AdminBenchmark />} />
          <Route path="/admin/questions" element={<AdminQuestions />} />
          <Route path="/admin/chatlogs" element={<AdminChatLogs />} />
          <Route path="/admin/users" element={<AdminUsers />} />
          <Route path="/admin/config" element={<AdminConfig />} />
          <Route path="/admin/docker" element={<AdminDocker />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
