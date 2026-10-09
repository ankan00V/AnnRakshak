import { AlertTriangle, ArrowRight, Inbox, Loader2, TrendingUp, UserPlus } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useState } from 'react'
import { api } from '../../api/client'
import { useAsync } from '../../lib/hooks'
import { Card, ErrorBox } from '../../ui/kit'
import { Kpis, KpisSkeleton, PanelBone } from '../panels'
import { Download } from 'lucide-react'

/** What needs a person today, in the order it should be dealt with. The numbers
 *  come after: a supervisor opens this to find work, not to admire a total. */
export default function Today() {
  const work = useAsync(() => api.worklist(), [])
  const summary = useAsync(() => api.summary(), [])
  const [routing, setRouting] = useState(false)
  const [routed, setRouted] = useState<string | null>(null)

  const route = async () => {
    setRouting(true)
    try {
      const r = await api.routeCases()
      setRouted(r.assigned === 0 ? 'Nothing waiting to be routed.'
        : `${r.assigned} case${r.assigned === 1 ? '' : 's'} routed to the freest officers.`)
      work.reload()
    } finally {
      setRouting(false)
    }
  }

  // Four rows reading "0" is a scoreboard again; say it once instead.
  const clear = !work.data ? [] : [
    work.data.overdue_count === 0,
    work.data.unrouted.length === 0,
    work.data.pending_officers === 0,
    work.data.unnamed_problems === 0,
  ].filter(Boolean)

  return (
    <>
      {work.error && <Card className="p-4"><ErrorBox error={work.error} onRetry={work.reload} /></Card>}

      {!work.data ? <PanelBone rows={6} /> : (
        <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr]">
          <Card className="p-4 md:p-5">
            <h2 className="font-semibold">Needs a person</h2>
            <p className="text-xs text-soil-dark/60 mt-0.5">
              A farmer who has waited more than {work.data.sla_hours} hours for a human has waited too long.
            </p>

            {clear.length === 4 ? (
              <p className="mt-4 rounded-2xl bg-leaf/5 border border-leaf/25 p-4 text-sm text-leaf-deep">
                All clear: nothing overdue, every case on a desk, no officer waiting to be verified,
                and no problem the model could not name.
              </p>
            ) : null}
            <ul className={`mt-4 divide-y divide-soil-dark/10 ${clear.length === 4 ? 'hidden' : ''}`}>
              <Row
                icon={AlertTriangle}
                tone={work.data.overdue_count > 0 ? 'ember' : 'leaf'}
                title={`${work.data.overdue_count} case${work.data.overdue_count === 1 ? '' : 's'} past ${work.data.sla_hours} h`}
                sub={work.data.overdue_cases.length > 0
                  ? `Longest: #${work.data.overdue_cases[0].id} in ${work.data.overdue_cases[0].district}, ${Math.round(work.data.overdue_cases[0].hours)} h`
                  : 'Every open case is inside the window.'}
                action={work.data.overdue_count > 0
                  ? <Link to="/expert" className="text-sm font-medium text-leaf-deep flex items-center gap-1">Open queue <ArrowRight className="w-3.5 h-3.5" /></Link>
                  : null}
              />

              <Row
                icon={Inbox}
                tone={work.data.unrouted.length > 0 ? 'ochre' : 'leaf'}
                title={`${work.data.unrouted.length} case${work.data.unrouted.length === 1 ? '' : 's'} on nobody's desk`}
                sub={work.data.unrouted.length > 0
                  ? 'No officer has been given these yet.'
                  : 'Every case has a name against it.'}
                action={work.data.unrouted.length > 0 ? (
                  <button onClick={route} disabled={routing}
                    className="flex items-center gap-1.5 rounded-full bg-leaf-deep text-cream text-xs font-medium px-3 py-1.5 disabled:opacity-60">
                    {routing && <Loader2 className="w-3.5 h-3.5 animate-spin" />} Route them
                  </button>
                ) : null}
              />

              <Row
                icon={UserPlus}
                tone={work.data.pending_officers > 0 ? 'ochre' : 'leaf'}
                title={`${work.data.pending_officers} officer${work.data.pending_officers === 1 ? '' : 's'} waiting to be verified`}
                sub="Until the office verifies them they review nothing and are handed no cases."
                action={work.data.pending_officers > 0
                  ? <Link to="/officer/officers" className="text-sm font-medium text-leaf-deep flex items-center gap-1">Review <ArrowRight className="w-3.5 h-3.5" /></Link>
                  : null}
              />

              <Row
                icon={TrendingUp}
                tone={work.data.unnamed_problems > 0 ? 'ochre' : 'leaf'}
                title={`${work.data.unnamed_problems} problem${work.data.unnamed_problems === 1 ? '' : 's'} the model cannot name`}
                sub="Closed by an officer as something outside the knowledge base."
                action={work.data.unnamed_problems > 0
                  ? <Link to="/officer/model" className="text-sm font-medium text-leaf-deep flex items-center gap-1">See them <ArrowRight className="w-3.5 h-3.5" /></Link>
                  : null}
              />
            </ul>
            {routed && <p className="mt-3 text-xs text-leaf-deep">{routed}</p>}
          </Card>

          <Card className="p-4 md:p-5">
            <h2 className="font-semibold">Building this week</h2>
            <p className="text-xs text-soil-dark/60 mt-0.5">
              High-risk alerts by problem, across the district's farms.
            </p>
            {work.data.building.length === 0 ? (
              <p className="mt-4 text-sm text-soil-dark/70">Nothing is building — no high alert in seven days.</p>
            ) : (
              <ul className="mt-4 space-y-2.5">
                {work.data.building.map((b) => (
                  <li key={b.target} className="flex items-center justify-between gap-3">
                    <span className="min-w-0">
                      <span className="block text-sm font-medium truncate">{b.name}</span>
                      <span className="block text-[11px] text-soil-dark/60">{b.crop}</span>
                    </span>
                    <span className="flex items-center gap-2 shrink-0">
                      <Link to={`/officer/queue?target=${b.target}`}
                        className="text-xs tabular-nums text-soil-dark/70 hover:text-leaf-deep hover:underline underline-offset-2">
                        {b.farms} farms
                      </Link>
                      <Link to={`/officer/advisories?target=${b.target}&crop=${b.crop}`}
                        className="rounded-full bg-ochre/15 text-[#8a5a17] text-xs font-medium px-3 py-1.5 hover:bg-ochre/25">
                        Advise
                      </Link>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}

      {summary.data ? <Kpis s={summary.data} /> : !summary.error && <KpisSkeleton />}
      <TrendStrip />
    </>
  )
}

/** A number with no direction is a poster. This week against the last, and the
 *  fortnight behind it. */
function TrendStrip() {
  const t = useAsync(() => api.trends(), [])
  if (!t.data) return <PanelBone rows={3} />
  const items = [
    { label: 'New cases', s: t.data.cases },
    { label: 'Alerts raised', s: t.data.alerts },
    { label: 'Expert verdicts', s: t.data.verdicts },
  ]
  return (
    <Card className="p-4 md:p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-semibold">This week against last</h2>
          <p className="text-xs text-soil-dark/60 mt-0.5">The fortnight to date, a bar a day.</p>
        </div>
        <a href="/api/officials/report" download
          className="flex items-center gap-1.5 rounded-full border border-soil-dark/20 px-3 py-1.5 text-xs font-medium hover:bg-soil-dark/5">
          <Download className="w-3.5 h-3.5" /> The week as a file
        </a>
      </div>
      <div className="mt-4 grid gap-5 sm:grid-cols-3">
        {items.map(({ label, s }) => {
          const top = Math.max(1, ...s.series)
          const up = (s.change_pct ?? 0) > 0
          return (
            <div key={label}>
              <p className="text-xs text-soil-dark/60">{label}</p>
              <p className="mt-0.5 flex items-baseline gap-2">
                <span className="text-2xl font-semibold tabular-nums">{s.this_week}</span>
                {s.change_pct != null && (
                  <span className={`text-xs font-medium ${up ? 'text-ember' : 'text-leaf-deep'}`}>
                    {up ? '+' : ''}{s.change_pct}% on last week
                  </span>
                )}
              </p>
              <div className="mt-2 flex items-end gap-[3px] h-10" aria-hidden>
                {s.series.map((n, i) => (
                  <span key={i} className={`flex-1 rounded-sm ${i >= s.series.length / 2 ? 'bg-leaf-deep/70' : 'bg-soil-dark/15'}`}
                    style={{ height: `${Math.max(6, (n / top) * 100)}%` }} />
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

const TONES = {
  ember: 'bg-ember/10 text-ember',
  ochre: 'bg-ochre/15 text-[#8a5a17]',
  leaf: 'bg-leaf/10 text-leaf-deep',
}

function Row({ icon: Icon, tone, title, sub, action }: {
  icon: typeof AlertTriangle; tone: keyof typeof TONES; title: string; sub: string; action: React.ReactNode
}) {
  return (
    <li className="flex items-center gap-3 py-3">
      <span className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${TONES[tone]}`}>
        <Icon className="w-4 h-4" />
      </span>
      <span className="flex-1 min-w-0">
        <span className="block text-sm font-medium">{title}</span>
        <span className="block text-xs text-soil-dark/60">{sub}</span>
      </span>
      {action}
    </li>
  )
}
