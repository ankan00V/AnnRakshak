import { useState } from 'react'
import { BrainCircuit, ClipboardList, Loader2, Map as MapIcon, Megaphone, Package, RefreshCw, Sunrise, Users } from 'lucide-react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { api } from '../api/client'
import type { Summary, Worklist } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import AccountMenu from '../auth/AccountMenu'
import { useAsync } from '../lib/hooks'
import Darpan from './Darpan'
import { Toasts } from '../ui/Toast'
import BrandMark from '../ui/BrandMark'

/** The district office, laid out as a desk rather than as a brochure.
 *
 *  The farmer app is a warm single column read on a phone at the edge of a
 *  field, and it should stay that. This is the other job: hundreds of farms, a
 *  queue, a staff roster and a decision to make before the afternoon. So it is
 *  deliberately not the same design — dark working chrome instead of cream, a
 *  rail that carries its counts so an officer sees where the work is standing
 *  before choosing a screen, and the district's live state across the top of
 *  every page.
 */
const TABS: { to: string; end?: boolean; icon: typeof Sunrise; label: string; count?: 'queue' | 'gaps' | 'officers' }[] = [
  { to: '/officer', end: true, icon: Sunrise, label: 'Today' },
  { to: '/officer/queue', icon: ClipboardList, label: 'Queue', count: 'queue' },
  { to: '/officer/map', icon: MapIcon, label: 'Map' },
  { to: '/officer/advisories', icon: Megaphone, label: 'Advisories' },
  { to: '/officer/inputs', icon: Package, label: 'Inputs' },
  { to: '/officer/model', icon: BrainCircuit, label: 'Model & gaps', count: 'gaps' },
  { to: '/officer/officers', icon: Users, label: 'Officers', count: 'officers' },
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
      setSweep(`${r.alerts_issued} new alerts across ${r.farms} farms · weather: ${src}`)
      work.reload()
      summary.reload()
    } finally {
      setSweeping(false)
    }
  }

  return (
    <Toasts>
    <div className="min-h-screen bg-[#efe9dd] text-soil-dark">
      <header className="sticky top-0 z-30 bg-soil-dark text-cream">
        <div className="flex items-center justify-between gap-3 px-4 lg:px-6 h-14 lg:h-16">
          <div className="flex items-center gap-2.5 min-w-0">
            <Link to="/" className="shrink-0"><BrandMark size={30} /></Link>
            <span className="min-w-0">
              <span className="block font-semibold tracking-tight leading-none">AnnRakshak</span>
              <span className="hidden sm:block text-[11px] text-cream/55 truncate">
                District office{states.length ? ` · ${states.join(' · ')}` : ''}
              </span>
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={runSweep} disabled={sweeping} title="Score every farm against today's weather"
              className="flex items-center gap-2 rounded-full bg-ochre text-cream text-sm font-medium px-3.5 py-2 disabled:opacity-60 hover:brightness-110 transition">
              {sweeping ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
              <span className="hidden sm:inline">Run risk sweep</span>
            </button>
            <AccountMenu />
          </div>
        </div>

        {/* Phone and tablet: the rail lies down under the header. */}
        <nav className="lg:hidden flex gap-1 px-2 overflow-x-auto no-scrollbar border-t border-cream/10">
          {TABS.map(({ to, end, icon: Icon, label, count }) => (
            <NavLink key={to} to={to} end={end}
              className={({ isActive }) => `flex items-center gap-2 whitespace-nowrap px-3 py-2.5 text-sm border-b-2 transition-colors ${
                isActive ? 'border-ochre text-cream font-medium' : 'border-transparent text-cream/60'}`}>
              <Icon className="w-4 h-4" />
              {label}
              {count && counts[count] ? <Badge n={counts[count]!} /> : null}
            </NavLink>
          ))}
        </nav>
      </header>

      <nav className="hidden lg:flex flex-col gap-1 fixed left-0 top-16 bottom-0 w-56 bg-soil-dark/95 px-3 pt-4">
        {TABS.map(({ to, end, icon: Icon, label, count }) => (
          <NavLink key={to} to={to} end={end}
            className={({ isActive }) => `flex items-center gap-3 rounded-xl px-3 min-h-[42px] text-[14px] transition-colors ${
              isActive ? 'bg-cream/10 text-cream font-medium' : 'text-cream/60 hover:text-cream hover:bg-cream/5'}`}>
            {({ isActive }) => (
              <>
                <Icon className={`w-[18px] h-[18px] shrink-0 ${isActive ? 'text-ochre' : ''}`} strokeWidth={isActive ? 2.4 : 2} />
                <span className="flex-1">{label}</span>
                {count && counts[count] ? <Badge n={counts[count]!} /> : null}
              </>
            )}
          </NavLink>
        ))}
        <p className="mt-auto mb-4 px-3 text-[10.5px] leading-relaxed text-cream/35">
          Every number here is this district's own, read live. Nothing reaches a farmer
          without an officer's name on it.
        </p>
      </nav>

      <main className="px-4 py-5 lg:pl-[calc(14rem+2.5rem)] lg:pr-10 lg:pt-7 lg:pb-16">
        <div className="lg:mx-auto lg:max-w-6xl space-y-5 lg:space-y-7">
          <Standing work={work.data} summary={summary.data} />
          {sweep && <div className="rounded-xl bg-leaf/10 text-leaf-deep text-sm px-4 py-2">{sweep}</div>}
          <div key={key} className="animate-fadein space-y-5 lg:space-y-7">
            <Outlet />
          </div>
        </div>
      </main>

      {/* The officers' own assistant. Krishi belongs to the farmers. */}
      <Darpan />
    </div>
    </Toasts>
  )
}

function Badge({ n }: { n: number }) {
  return (
    <span className="min-w-[20px] h-5 px-1.5 rounded-full bg-ochre/90 text-soil-dark text-[11px] font-semibold tabular-nums
                     flex items-center justify-center shrink-0">
      {n > 99 ? '99+' : n}
    </span>
  )
}

/** Where the district stands, on every screen: five numbers, each a door to
 *  the screen that settles it. A scoreboard would be decoration; these are the
 *  things an officer is answerable for. */
function Standing({ work, summary }: { work: Worklist | null; summary: Summary | null }) {
  const cells = [
    { label: 'Open cases', v: summary?.totals.open_cases, to: '/officer/queue', warn: false },
    { label: 'Past SLA', v: work?.overdue_count, to: '/officer/queue?overdue=1', warn: (work?.overdue_count ?? 0) > 0 },
    { label: 'Unassigned', v: work?.unrouted.length, to: '/officer', warn: (work?.unrouted.length ?? 0) > 0 },
    { label: 'Officers waiting', v: work?.pending_officers, to: '/officer/officers', warn: (work?.pending_officers ?? 0) > 0 },
    { label: 'Farms watched', v: summary?.totals.farms, to: '/officer/map', warn: false },
  ]
  return (
    <section aria-label="District standing"
      className="rounded-2xl bg-white border border-soil-dark/10 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5
                 divide-x divide-y sm:divide-y-0 divide-soil-dark/10 overflow-hidden">
      {cells.map(({ label, v, to, warn }) => (
        <Link key={label} to={to} className="px-4 py-3 hover:bg-cream transition-colors">
          <p className="text-[10.5px] font-semibold uppercase tracking-[0.1em] text-soil-dark/45">{label}</p>
          <p className={`mt-1 text-[26px] leading-none font-semibold tabular-nums ${warn ? 'text-ember' : 'text-soil-dark'}`}>
            {v == null ? <span className="inline-block w-10 h-6 rounded bg-soil-dark/10 animate-pulse" /> : v}
          </p>
        </Link>
      ))}
    </section>
  )
}
