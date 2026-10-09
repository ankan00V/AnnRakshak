import { useState } from 'react'
import { BookOpen, BrainCircuit, ClipboardCheck, ClipboardList, Loader2, Map as MapIcon, Megaphone, Package, RefreshCw, Users } from 'lucide-react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { api } from '../api/client'
import AccountMenu from '../auth/AccountMenu'
import Darpan from './Darpan'
import { Toasts } from '../ui/Toast'
import BrandMark from '../ui/BrandMark'

/** The officer console is a workplace, not a poster: one screen per job, and
 *  the whole district's surveillance no longer arrives as a single scroll. */
const TABS = [
  { to: '/officer', end: true, icon: ClipboardList, label: 'Today' },
  { to: '/officer/queue', icon: ClipboardCheck, label: 'Queue' },
  { to: '/officer/map', icon: MapIcon, label: 'Map' },
  { to: '/officer/advisories', icon: Megaphone, label: 'Advisories' },
  { to: '/officer/inputs', icon: Package, label: 'Inputs' },
  { to: '/officer/model', icon: BrainCircuit, label: 'Model & gaps' },
  { to: '/officer/officers', icon: Users, label: 'Officers' },
  { to: '/officer/reference', icon: BookOpen, label: 'Reference' },
]

export default function OfficerShell() {
  const [sweep, setSweep] = useState<string | null>(null)
  const [sweeping, setSweeping] = useState(false)
  const { key } = useLocation()

  const runSweep = async () => {
    setSweeping(true)
    try {
      const r = await api.runAll()
      const src = Object.entries(r.weather_sources).map(([k, v]) => `${v} ${k}`).join(', ')
      setSweep(`${r.alerts_issued} new alerts across ${r.farms} farms · weather: ${src}`)
    } finally {
      setSweeping(false)
    }
  }

  return (
    <Toasts>
    <div className="min-h-screen bg-[#f3efe6] text-soil-dark">
      <header className="bg-leaf-deep text-cream">
        <div className="max-w-7xl mx-auto px-4 md:px-6 py-3 flex flex-wrap gap-3 items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight">
              <BrandMark size={30} />AnnRakshak
            </Link>
            <span className="text-cream/40">/</span>
            <span className="text-sm">Crop-health surveillance · Maharashtra</span>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={runSweep} disabled={sweeping}
              className="flex items-center gap-2 rounded-full bg-ochre text-cream text-sm font-medium px-4 py-2 disabled:opacity-60">
              {sweeping ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
              Run risk sweep
            </button>
            <AccountMenu />
          </div>
        </div>

        <nav className="max-w-7xl mx-auto px-2 md:px-4 flex gap-1 overflow-x-auto no-scrollbar">
          {TABS.map(({ to, end, icon: Icon, label }) => (
            <NavLink key={to} to={to} end={end}
              className={({ isActive }) => `flex items-center gap-2 whitespace-nowrap px-3 py-2.5 text-sm border-b-2 transition-colors ${
                isActive ? 'border-ochre text-cream font-medium' : 'border-transparent text-cream/60 hover:text-cream'}`}>
              <Icon className="w-4 h-4" />
              {label}
            </NavLink>
          ))}
        </nav>
      </header>

      <div className="max-w-7xl mx-auto px-4 md:px-6 py-5 space-y-5">
        {sweep && <div className="rounded-xl bg-leaf/10 text-leaf-deep text-sm px-4 py-2">{sweep}</div>}
        <div key={key} className="animate-fadein space-y-5">
          <Outlet />
        </div>
      </div>

      {/* The officers' own assistant. Krishi belongs to the farmers. */}
      <Darpan />
    </div>
    </Toasts>
  )
}
