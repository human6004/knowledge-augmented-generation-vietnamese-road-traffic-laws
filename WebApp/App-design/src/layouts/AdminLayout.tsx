import LogoMark from '../components/LogoMark';
import { NavLink, Outlet } from 'react-router-dom'
import { AdminProvider, useAdmin } from '../admin/store'

const navItems = [
  { to: '/admin/dashboard', label: 'Tổng quan' },
  { to: '/admin/knowledge', label: 'Văn bản & tri thức KAG' },
  { to: '/admin/graph', label: 'Đồ thị tri thức' },
  { to: '/admin/pipeline', label: 'Pipeline & tác vụ' },
  { to: '/admin/benchmark', label: 'Benchmark' },
  { to: '/admin/questions', label: 'Ngân hàng câu hỏi' },
  { to: '/admin/chatlogs', label: 'Nhật ký chat' },
  { to: '/admin/users', label: 'Người dùng' },
  { to: '/admin/docker', label: 'Đóng gói Docker' },
  { to: '/admin/config', label: 'Cấu hình' },
]

export default function AdminLayout() {
  return (
    <AdminProvider>
      <Shell />
    </AdminProvider>
  )
}

function Toast() {
  const { toast, jobs } = useAdmin()
  const running = jobs.filter((j) => j.status === 'running').length
  return (
    <>
      {running > 0 && (
        <NavLink to="/admin/pipeline" className="mx-3 mb-3 flex items-center gap-2 rounded-xl border border-accent/40 bg-selected px-3 py-2 text-xs font-medium text-accent-strong">
          <span className="w-2 h-2 rounded-full bg-accent animate-pulse" /> {running} tác vụ đang chạy
        </NavLink>
      )}
      {toast && (
        <div role="status" className="fixed bottom-16 left-1/2 -translate-x-1/2 z-[70] rounded-full bg-navy text-bg px-4 py-2 text-[13px] font-medium shadow-lg">
          {toast}
        </div>
      )}
    </>
  )
}

function Shell() {
  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'var(--color-bg)' }}>
      {/* Sidebar */}
      <aside
        className="flex flex-col w-60 shrink-0 h-full border-r border-line"
        style={{ background: 'var(--color-sidebar)' }}
      >
        {/* Logo */}
        <div className="px-5 pt-6 pb-1">
          <span className="flex items-center gap-2 font-sans font-semibold text-[22px] tracking-normal text-navy">
            <LogoMark size={18} />
            LuậtGT
          </span>
          <p className="text-xs text-muted mt-0.5">Quản trị</p>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 mt-4 space-y-1">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `block px-3 py-2 rounded-lg text-[13.5px] transition-colors ${
                  isActive
                    ? 'text-navy bg-selected font-medium'
                    : 'text-text-secondary hover:bg-selected/70'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <Toast />
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
