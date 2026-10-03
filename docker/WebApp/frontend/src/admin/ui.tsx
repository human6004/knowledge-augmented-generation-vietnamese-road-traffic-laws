import { useEffect } from 'react'

export function Page({ title, subtitle, actions, children }: { title: string; subtitle?: string; actions?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="px-5 md:px-8 py-7 min-h-full bg-bg">
      <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-navy">{title}</h1>
          {subtitle && <p className="mt-1 text-[13px] text-muted">{subtitle}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </div>
  )
}

export function Card({ title, right, className = '', children }: { title?: string; right?: React.ReactNode; className?: string; children: React.ReactNode }) {
  return (
    <section className={`min-w-0 bg-surface rounded-2xl border border-line shadow-[0_1px_2px_rgba(53,45,36,0.04)] ${className}`}>
      {title && (
        <header className="flex items-center justify-between gap-2 px-5 pt-4 pb-3">
          <h2 className="text-sm font-semibold text-navy">{title}</h2>
          {right}
        </header>
      )}
      {children}
    </section>
  )
}

type BtnVariant = 'primary' | 'dark' | 'ghost' | 'outline' | 'danger'
const btn: Record<BtnVariant, string> = {
  primary: 'bg-accent text-navy hover:bg-accent-hover',
  dark: 'bg-navy text-bg hover:bg-navy-light',
  ghost: 'text-navy underline underline-offset-4 decoration-navy/40 hover:bg-selected hover:decoration-navy',
  outline: 'border border-navy/35 bg-selected text-navy hover:border-navy/60 hover:bg-line',
  danger: 'text-red-700 underline underline-offset-4 decoration-red-700/40 hover:bg-red-50 hover:decoration-red-700',
}
export function Button({ variant = 'outline', size = 'md', className = '', ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant; size?: 'sm' | 'md' }) {
  return (
    <button
      {...p}
      className={`inline-flex items-center justify-center gap-1.5 rounded-md font-semibold cursor-pointer transition-colors disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-strong focus-visible:ring-offset-2 ${
        size === 'sm' ? 'min-h-8 px-3 py-1.5 text-xs' : 'min-h-10 px-4 py-2 text-[13px]'
      } ${btn[variant]} ${className}`}
    />
  )
}

const tones = {
  green: 'text-emerald-700',
  amber: 'text-amber-700',
  red: 'text-red-700',
  gray: 'text-text-secondary',
  gold: 'text-accent-strong',
}
export type Tone = keyof typeof tones
export function Badge({ tone = 'gray', children }: { tone?: Tone; children: React.ReactNode }) {
  return (
    <span className={`inline-block whitespace-nowrap text-xs font-medium ${tones[tone]}`}>
      {children}
    </span>
  )
}

export function Modal({ open, title, onClose, children, footer }: { open: boolean; title: string; onClose: () => void; children: React.ReactNode; footer?: React.ReactNode }) {
  useEffect(() => {
    if (!open) return
    const h = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', h)
    return () => document.removeEventListener('keydown', h)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-[60] grid place-items-center p-4 bg-navy/30 backdrop-blur-[2px]" onMouseDown={onClose}>
      <div role="dialog" aria-label={title} className="w-full max-w-lg max-h-[90vh] flex flex-col rounded-2xl bg-bg border border-line shadow-2xl" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-line">
          <h3 className="text-[15px] font-semibold text-navy">{title}</h3>
          <button onClick={onClose} aria-label="Đóng" className="p-1.5 rounded-lg text-muted hover:bg-selected hover:text-navy">✕</button>
        </div>
        <div className="p-5 overflow-y-auto">{children}</div>
        {footer && <div className="flex justify-end gap-2 px-5 py-3 border-t border-line">{footer}</div>}
      </div>
    </div>
  )
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-xs font-medium text-text-secondary mb-1.5">{label}</span>
      {children}
      {hint && <span className="block mt-1 text-[11.5px] text-muted">{hint}</span>}
    </label>
  )
}

export const inputCls = 'w-full rounded-xl border border-line bg-white/70 px-3 py-2 text-[13.5px] text-navy outline-none placeholder:text-muted/70 focus:border-accent focus:ring-4 focus:ring-accent/10 transition'

export function Th({ children, className = '' }: { children?: React.ReactNode; className?: string }) {
  return <th className={`text-left px-4 py-2.5 text-[11.5px] font-medium uppercase tracking-wide text-muted ${className}`}>{children}</th>
}
export function Td({ children, className = '' }: { children?: React.ReactNode; className?: string }) {
  return <td className={`px-4 py-3 text-[13.5px] ${className}`}>{children}</td>
}

export function Progress({ value, tone = 'accent' }: { value: number; tone?: 'accent' | 'green' | 'red' }) {
  const c = tone === 'green' ? 'bg-emerald-500' : tone === 'red' ? 'bg-red-400' : 'bg-accent'
  return (
    <div className="h-1.5 w-full rounded-full bg-line overflow-hidden">
      <div className={`h-full ${c} transition-[width] duration-500`} style={{ width: `${value}%` }} />
    </div>
  )
}

export function Terminal({ lines, className = '' }: { lines: string[]; className?: string }) {
  return (
    <pre className={`rounded-xl bg-[#2a241d] text-[#f3e7c7] font-mono text-[11.5px] leading-relaxed p-4 overflow-auto whitespace-pre-wrap ${className}`}>
      {lines.map((l, i) => (
        <div key={i} className={l.startsWith('$') ? 'text-accent' : l.startsWith('✓') ? 'text-emerald-300' : l.startsWith('✗') ? 'text-red-300' : ''}>{l}</div>
      ))}
    </pre>
  )
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label?: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`relative w-9 h-5 rounded-full transition-colors ${checked ? 'bg-accent' : 'bg-line'}`}
    >
      <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${checked ? 'translate-x-4' : ''}`} />
    </button>
  )
}
