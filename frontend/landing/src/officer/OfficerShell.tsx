import { useState } from 'react'
import { BrainCircuit, ClipboardList, Loader2, Map as MapIcon, Megaphone, Package, RefreshCw, Sunrise, Users } from 'lucide-react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { api } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import AccountMenu from '../auth/AccountMenu'
import { useAsync } from '../lib/hooks'
import { many } from './panels'
import Darpan from './Darpan'
import { Toasts } from '../ui/Toast'
import BrandMark from '../ui/BrandMark'

/** The district office, laid out as a desk rather than as a brochure.
 *
 *  The same family as the farmer app — the green frame, white cards, the serif
 *  page titles — so the two read as one product. What differs is density: this
 *  is hundreds of farms, a queue and a staff roster on a laptop, so the frame
 *  carries the counts, and each page opens on what needs a person.
 */
const TABS: { to: string; end?: boolean; icon: typeof Sunrise; label: string;
  count?: 'queue' | 'gaps' | 'officers'; supervisorOnly?: boolean }[] = [
  { to: '/officer', end: true, icon: Sunrise, label: 'Today' },
  { to: '/officer/queue', icon: ClipboardList, label: 'Queue', count: 'queue' },
  { to: '/officer/map', icon: MapIcon, label: 'Map' },
  { to: '/officer/advisories', icon: Megaphone, label: 'Advisories' },
  { to: '/officer/inputs', icon: Package, label: 'Inputs' },
  { to: '/officer/model', icon: BrainCircuit, label: 'Model & gaps', count: 'gaps' },
  // Staffing — colleagues' names, their loads, who is waiting to be let in —
  // is the office's business and not every officer's.
  { to: '/officer/officers', icon: Users, label: 'Officers', count: 'officers', supervisorOnly: true },
]

export default function OfficerShell() {
  const { me } = useAuth()
  const [sweep, setSweep] = useState<string | null>(null)
  const [sweeping, setSweeping] = useState(false)
  const { key } = useLocation()
  // Both reads are cached under a name the screens share, so the rail and the
  // strip cost nothing on top of the page you opened.
  const work = useAsync(() => api.worklist(), [], 'worklist')
  const summary = useAsync(() => api.summary(), [], 'summary')
  const states = me?.profile?.states ?? []

  const boss = me?.profile?.supervisor === true
  const tabs = TABS.filter((t) => !t.supervisorOnly || boss)

  const counts: Record<string, number | null> = {
    queue: summary.data?.totals.open_cases ?? null,
    gaps: work.data?.unnamed_problems ?? null,
    officers: work.data?.pending_officers ?? null,
  }

  const runSweep = async () => {
    setSweeping(true)
    try {
      const r = await api.runAll()
      const src = Object.entries(r.weather_sources).map(([k, v]) => `${v} ${k}`).join(', ')
      setSweep(`${many(r.alerts_issued, 'new alert')} across ${many(r.farms, 'farm')} · weather: ${src}`)
      work.reload()
      summary.reload()
    } finally {
      setSweeping(false)
    }
  }

  return (
    <Toasts>
    <div className="min-h-screen bg-[#1d4a2c] text-soil-dark">
      <header className="fixed inset-x-0 top-0 z-30 bg-[#1d4a2c] text-white">
        <div className="flex h-16 items-center justify-between gap-3 px-4 lg:px-5">
          <div className="flex min-w-0 items-center gap-3">
            {/* The mark is the only thing inside, so without a name this link
                reaches a screen reader as "link" and nothing else. */}
            <Link to="/" aria-label="AnnRakshak" className="shrink-0"><BrandMark size={38} /></Link>
            <span className="min-w-0">
              <span className="block text-[18px] font-semibold leading-tight tracking-tight">AnnRakshak</span>
              <span className="block truncate text-[12px] text-white/70">
                District office{states.length ? ` · ${states.join(' · ')}` : ''}
              </span>
            </span>
          </div>
          <div className="flex items-center gap-2.5">
            {boss && <button onClick={runSweep} disabled={sweeping} title="Score every farm against today's weather"
              className="flex min-h-[40px] items-center gap-2 rounded-full bg-[#d29a3a] px-4 text-[14px] font-semibold text-white shadow-[0_6px_16px_-8px_rgba(0,0,0,0.5)] transition hover:brightness-110 disabled:opacity-60">
              {sweeping ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              <span className="hidden sm:inline">Run risk sweep</span>
            </button>}
            <AccountMenu profile={{ to: '/officer/profile', label: 'My record' }} />
          </div>
        </div>

        {/* Phone and tablet: the rail lies down under the header. */}
        <nav className="no-scrollbar flex gap-1.5 overflow-x-auto px-3 pb-2.5 lg:hidden">
          {tabs.map(({ to, end, icon: Icon, label, count }) => (
            <NavLink key={to} to={to} end={end}
              className={({ isActive }) => `flex min-h-[38px] items-center gap-2 whitespace-nowrap rounded-full px-3.5 text-[14px] transition-colors ${
                isActive ? 'bg-[#d29a3a] font-semibold text-white' : 'text-white/80 hover:bg-white/10'}`}>
              {({ isActive }) => (
                <>
                  <Icon className="h-4 w-4" />
                  {label}
                  {count && counts[count] ? <Badge n={counts[count]!} on={isActive} /> : null}
                </>
              )}
            </NavLink>
          ))}
        </nav>
      </header>

      <nav className="fixed bottom-0 left-0 top-16 hidden w-60 flex-col gap-1 px-3 pt-4 lg:flex">
        {tabs.map(({ to, end, icon: Icon, label, count }) => (
          <NavLink key={to} to={to} end={end}
            className={({ isActive }) => `flex min-h-[48px] items-center gap-3 rounded-2xl px-3.5 text-[15px] transition-colors ${
              isActive ? 'bg-[#d29a3a] font-semibold text-white shadow-[0_8px_18px_-10px_rgba(0,0,0,0.55)]' : 'text-white/80 hover:bg-white/[0.07] hover:text-white'}`}>
            {({ isActive }) => (
              <>
                <Icon className="h-5 w-5 shrink-0" strokeWidth={isActive ? 2.2 : 1.8} />
                <span className="flex-1">{label}</span>
                {count && counts[count] ? <Badge n={counts[count]!} on={isActive} /> : null}
              </>
            )}
          </NavLink>
        ))}
        <p className="mb-5 mt-auto px-3.5 text-[12px] leading-relaxed text-white/55">
          Every number here is this district's own, read live. Nothing reaches a farmer
          without an officer's name on it.
        </p>
      </nav>

      {/* The working sheet: cream, its corner turned in against the green frame. */}
      <main className="pt-[7.25rem] lg:pl-60 lg:pt-16">
        <div className="relative min-h-[calc(100vh-4rem)] overflow-hidden bg-[#f4f1e8] lg:rounded-tl-[32px]">
          <img aria-hidden src="/photos/hills.webp" alt=""
            className="pointer-events-none absolute inset-x-0 top-0 h-56 w-full object-cover opacity-30 [mask-image:linear-gradient(to_bottom,black,transparent)]" />
          <div className="relative mx-auto max-w-[1240px] space-y-6 px-4 py-6 lg:px-10 lg:py-8">
            {sweep && <div role="status" className="rounded-2xl bg-[#e3efd9] px-4 py-3 text-[14px] text-leaf-deep">{sweep}</div>}
            <div key={key} className="animate-fadein space-y-6">
              <Outlet />
            </div>
          </div>
        </div>
      </main>

      {/* The officers' own assistant. Krishi belongs to the farmers. */}
      <Darpan />
    </div>
    </Toasts>
  )
}

function Badge({ n, on }: { n: number; on: boolean }) {
  return (
    <span className={`flex h-[22px] min-w-[22px] shrink-0 items-center justify-center rounded-full px-1.5 text-[12px] font-semibold tabular-nums ${
      on ? 'bg-white text-[#8a5a17]' : 'bg-[#d29a3a] text-white'}`}>
      {n > 99 ? '99+' : n}
    </span>
  )
}
