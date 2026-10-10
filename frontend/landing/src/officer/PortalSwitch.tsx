import { Link } from 'react-router-dom'
import { ClipboardCheck, LayoutDashboard } from 'lucide-react'

/** The two halves of an officer's work, and a way between them.
 *
 *  An officer signs in to one role and lands on the case console, but the
 *  district office — the queue, the map, the advisories, the staff — is a
 *  separate screen at /officer. The console linked to it; nothing linked back,
 *  so the way out was the logo and the public landing page. Both headers now
 *  carry this, so neither half is a dead end and it is always clear which one
 *  you are looking at.
 */
export function PortalSwitch({ here }: { here: 'review' | 'office' }) {
  const panes = [
    { id: 'review', to: '/expert', icon: ClipboardCheck, label: 'Case review', short: 'Cases' },
    { id: 'office', to: '/officer', icon: LayoutDashboard, label: 'District office', short: 'Office' },
  ] as const

  return (
    <nav aria-label="Officer workspaces"
      className="flex items-center gap-0.5 rounded-full bg-cream/10 p-0.5 ring-1 ring-cream/15">
      {panes.map(({ id, to, icon: Icon, label, short }) => {
        const active = id === here
        return (
          <Link key={id} to={to} aria-current={active ? 'page' : undefined}
            title={active ? `${label} — you are here` : `Go to ${label}`}
            className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium whitespace-nowrap transition-colors ${
              active ? 'bg-cream text-soil-dark' : 'text-cream/70 hover:text-cream'}`}>
            <Icon className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">{label}</span>
            <span className="sm:hidden">{short}</span>
          </Link>
        )
      })}
    </nav>
  )
}
