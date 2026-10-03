import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import { homeFor, type Role, type Session } from './auth-policy'
import { api, send, tokenKey } from './api'
type User = { email: string; name: string; role: 'ADMIN' | 'USER' }
const profile = (u: User): Session => ({ email: u.email, name: u.name, role: u.role === 'ADMIN' ? 'admin' : 'user' })
const Context = createContext<{ session: Session | null; ready: boolean; login: (email: string, password: string) => Promise<void>; register: (name: string, email: string, password: string) => Promise<void>; logout: () => Promise<void> } | null>(null)
export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null), [ready, setReady] = useState(false)
  useEffect(() => {
    let mounted = true
    if (sessionStorage.getItem(tokenKey)) api<User>('/auth/me').then(u => { if (mounted) setSession(profile(u)) }).catch(() => {}).finally(() => { if (mounted) setReady(true) })
    else setReady(true)
    const expire = () => { sessionStorage.removeItem('luatgt-active-exam'); setSession(null) }; window.addEventListener('luatgt-session-expired', expire)
    return () => { mounted = false; window.removeEventListener('luatgt-session-expired', expire) }
  }, [])
  async function authenticate(path: string, body: unknown) { const r = await api<{ accessToken: string; user: User }>(path, send('POST', body)); sessionStorage.removeItem('luatgt-active-exam'); sessionStorage.setItem(tokenKey, r.accessToken); setSession(profile(r.user)) }
  const login = (email: string, password: string) => authenticate('/auth/login', { email, password })
  const register = (name: string, email: string, password: string) => authenticate('/auth/register', { name, email, password })
  async function logout() { await api('/auth/logout', send('POST')); sessionStorage.removeItem(tokenKey); sessionStorage.removeItem('luatgt-active-exam'); setSession(null) }
  return <Context.Provider value={{ session, ready, login, register, logout }}>{children}</Context.Provider>
}
export function useAuth() { const auth = useContext(Context); if (!auth) throw new Error('AuthProvider required'); return auth }
export function RequireRole({ role }: { role: Role }) { const { session, ready } = useAuth(); if (!ready) return <p className="p-8" role="status">Đang kiểm tra phiên đăng nhập…</p>; if (!session) return <Navigate to="/login" replace />; return session.role === role ? <Outlet /> : <Navigate to={homeFor(session.role)} replace /> }
export function SessionHome() { const { session, ready } = useAuth(); return ready ? <Navigate to={session ? homeFor(session.role) : '/login'} replace /> : <p className="p-8">Đang tải…</p> }
export function AccountMenu({ collapsed = false }: { collapsed?: boolean }) {
  const { session, logout } = useAuth(); const [error, setError] = useState(''), [busy, setBusy] = useState(false)
  return <div className="border-t border-line p-3">{!collapsed && <div className="mb-2 text-xs text-muted"><p className="font-semibold text-navy">{session?.name}</p><p className="truncate mt-1">{session?.email}</p></div>}<button disabled={busy} onClick={async () => { setBusy(true); setError(''); try { await logout() } catch (e) { setError((e as Error).message) } finally { setBusy(false) } }} aria-label="Đăng xuất" title="Đăng xuất" className="w-full rounded-md border border-navy/35 px-2 py-2 text-xs hover:bg-selected focus-visible:outline-2 focus-visible:outline-accent">{collapsed ? '↪' : 'Đăng xuất'}</button>{error && <p role="alert" className="mt-2 text-xs text-red-700">{error}</p>}</div>
}
