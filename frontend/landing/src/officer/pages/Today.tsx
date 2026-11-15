import { AlertTriangle, ArrowRight, CalendarDays, CheckCircle2, ClipboardList, Inbox, Loader2, TrendingUp, UserPlus, Users } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useState } from 'react'
import { api } from '../../api/client'
import { useAsync } from '../../lib/hooks'
import { MAIN, SIDE, SPLIT } from '../../ui/layout'
import { useAuth } from '../../auth/AuthContext'
import { Card, ErrorBox } from '../../ui/kit'
import { Kpis, KpisSkeleton, many, PanelBone, StatCard } from '../panels'
import { Download } from 'lucide-react'

/** What needs a person today, in the order it should be dealt with. The numbers
 *  come after: a supervisor opens this to find work, not to admire a total. */
export default function Today() {
  const work = useAsync(() => api.worklist(), [])
  const summary = useAsync(() => api.summary(), [], 'summary')
  const { me } = useAuth()
  const [routing, setRouting] = useState(false)
  const [routed, setRouted] = useState<string | null>(null)
  const [routeFailed, setRouteFailed] = useState<string | null>(null)
  // Routing a backlog and verifying a colleague are supervisor decisions, so an
  // ordinary desk is told who does them rather than handed a button the server
  // will refuse.
  const supervisor = me?.profile?.supervisor === true

  const route = async () => {
    setRouting(true)
    setRouteFailed(null)
    setRouted(null)
    try {
      const r = await api.routeCases()
      setRouted(r.assigned === 0 ? 'Nothing waiting to be routed.'
        : `${r.assigned} case${r.assigned === 1 ? '' : 's'} routed to the freest officers.`)
      work.reload()
    } catch (e) {
      setRouteFailed(e instanceof Error ? e.message : 'Could not route the cases just now.')
    } finally {
      setRouting(false)
    }
  }


  const hour = new Date().getHours()
  const greet = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'
  const first = (me?.name ?? '').trim().split(/\s+/)[0]
  const today = new Date().toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
  const w = work.data
  const t = summary.data?.totals

  return (
    <>
      {/* The day's opening line, over the district's own fields. */}
      <section className="relative -mx-4 -mt-6 overflow-hidden px-4 pb-2 pt-6 lg:-mx-10 lg:-mt-8 lg:px-10 lg:pt-8">
        <img aria-hidden src="/photos/sunset.webp" alt=""
          className="pointer-events-none absolute right-0 top-0 hidden h-full w-[62%] object-cover object-[center_55%] opacity-90 [mask-image:linear-gradient(to_right,transparent,black_45%)] md:block" />
        <div className="relative flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="font-instrument-serif text-[38px] leading-none text-[#1d3a24] lg:text-[46px]">
              {greet}{first ? `, ${first}` : ''}
            </h1>
            <p className="mt-2 text-[15px] text-soil-dark/80">What needs a person in this district, in the order to deal with it.</p>
          </div>
          <p className="flex items-center gap-2 rounded-full bg-white/90 px-4 py-2 text-[14px] font-medium shadow-sm ring-1 ring-soil-dark/[0.07]">
            <CalendarDays className="h-4 w-4 text-[#2f6a39]" aria-hidden /> {today}
          </p>
        </div>
        <div className="relative mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
          <StatCard icon={AlertTriangle} tone="red" value={w?.overdue_count} label={`Past ${w?.sla_hours ?? 24} h`} to="/officer/queue?overdue=1" />
          <StatCard icon={Inbox} tone="amber" value={w?.unrouted.length} label="On nobody's desk" to="/officer/queue?scope=unassigned" />
          <StatCard icon={ClipboardList} tone="green" value={t?.open_cases} label="Open cases" to="/officer/queue" />
          <StatCard icon={Users} tone="violet" value={t?.farms} label="Farms watched" to="/officer/map" />
        </div>
      </section>

      {work.error && <Card className="p-4"><ErrorBox error={work.error} onRetry={work.reload} /></Card>}

      {!w ? <PanelBone rows={6} /> : (
        <div className={`gap-6 ${SPLIT}`}>
          <Card className={`p-5 lg:p-6 ${MAIN}`}>
            <h2 className="text-[22px] font-semibold tracking-tight">Needs attention</h2>
            <p className="mt-1 text-[14px] text-soil-dark/70">
              A farmer who has waited more than {w.sla_hours} hours for a person has waited too long.
            </p>
            <ul className="mt-4 space-y-2">
              <Row
                icon={AlertTriangle}
                tone={w.overdue_count > 0 ? 'ember' : 'leaf'}
                title={`${many(w.overdue_count, 'case')} past ${w.sla_hours} h`}
                sub={w.overdue_cases.length > 0
                  ? `Longest: #${w.overdue_cases[0].id} in ${w.overdue_cases[0].district}, ${Math.round(w.overdue_cases[0].hours)} h`
                  : 'Every open case is inside the window.'}
                to={w.overdue_count > 0 ? '/officer/queue?overdue=1' : undefined}
              />
              <Row
                icon={Inbox}
                tone={w.unrouted.length > 0 ? 'ochre' : 'leaf'}
                title={`${many(w.unrouted.length, 'case')} on nobody's desk`}
                sub={w.unrouted.length === 0
                  ? 'Every case has a name against it.'
                  : supervisor ? 'No officer has been given these yet.' : 'Waiting on your supervisor to place them.'}
                action={w.unrouted.length > 0 && supervisor ? (
                  <button onClick={route} disabled={routing}
                    className="flex min-h-[38px] shrink-0 items-center gap-1.5 rounded-full bg-[#2f6a39] px-4 text-[13px] font-semibold text-white hover:bg-[#2a5f33] disabled:opacity-60">
                    {routing && <Loader2 className="h-4 w-4 animate-spin" />} Route them
                  </button>
                ) : undefined}
              />
              <Row
                icon={UserPlus}
                tone={w.pending_officers > 0 ? 'ochre' : 'leaf'}
                title={`${many(w.pending_officers, 'officer')} waiting to be verified`}
                sub={w.pending_officers > 0 ? 'Until the office verifies them they review nothing and are handed no cases.' : 'All officers are verified.'}
                to={w.pending_officers > 0 && supervisor ? '/officer/officers' : undefined}
              />
              <Row
                icon={TrendingUp}
                tone={w.unnamed_problems > 0 ? 'ochre' : 'leaf'}
                title={`${many(w.unnamed_problems, 'problem')} the model cannot name`}
                sub={w.unnamed_problems > 0 ? 'Closed by an officer as something outside the knowledge base.' : 'Every case so far is within the knowledge base.'}
                to={w.unnamed_problems > 0 ? '/officer/model' : undefined}
              />
            </ul>
            {routed && <p className="mt-3 text-[14px] text-leaf-deep">{routed}</p>}
            {routeFailed && <p className="mt-3 text-[14px] text-ember">{routeFailed}</p>}
          </Card>

          <Card className={`p-5 lg:p-6 ${SIDE}`}>
            <h2 className="text-[20px] font-semibold tracking-tight">Building this week</h2>
            <p className="mt-1 text-[14px] text-soil-dark/70">High-risk alerts by problem, across the district's farms.</p>
            {w.building.length === 0 ? (
              <p className="mt-4 flex items-center gap-3 rounded-2xl bg-[#f1f6ec] p-4 text-[14px] text-soil-dark/85">
                <CheckCircle2 className="h-5 w-5 shrink-0 text-[#4b8b3b]" aria-hidden />
                Nothing is building — no high alert in seven days.
              </p>
            ) : (
              <ul className="mt-4 space-y-2">
                {w.building.map((b) => (
                  <li key={b.target} className="flex items-center justify-between gap-3 rounded-2xl bg-[#f8f6f0] p-3">
                    <span className="min-w-0">
                      <span className="block truncate text-[15px] font-semibold">{b.name}</span>
                      <Link to={`/officer/queue?target=${b.target}`}
                        className="text-[13px] text-soil-dark/70 hover:text-leaf-deep hover:underline underline-offset-2">
                        {b.crop} · {many(b.farms, 'farm')}
                      </Link>
                    </span>
                    <Link to={`/officer/advisories?target=${b.target}&crop=${b.crop}`}
                      className="shrink-0 rounded-full bg-[#fbe9c4] px-3.5 py-1.5 text-[13px] font-semibold text-[#7a4f12] hover:bg-[#f6dfae]">
                      Advise
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}

      {summary.data ? <Kpis s={summary.data} /> : !summary.error && <KpisSkeleton />}
      <TrendStrip supervisor={supervisor} />
    </>
  )
}

/** A number with no direction is a poster. This week against the last, and the
 *  fortnight behind it. */
function TrendStrip({ supervisor }: { supervisor: boolean }) {
  const t = useAsync(() => api.trends(), [])
  if (!t.data) return <PanelBone rows={3} />
  const items = [
    { label: 'New cases', s: t.data.cases },
    { label: 'Alerts raised', s: t.data.alerts },
    { label: 'Expert verdicts', s: t.data.verdicts },
  ]
  return (
    <Card className="p-5 lg:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-[20px] font-semibold tracking-tight">This week against last</h2>
          <p className="mt-1 text-[14px] text-soil-dark/70">The fortnight to date, a bar a day.</p>
        </div>
        {/* The endpoint is supervisor-only. Offering the button to everyone
            meant most officers pressed it and were handed a 403. */}
        {supervisor ? (
          <a href="/api/officials/report" download
            className="flex min-h-[40px] items-center gap-1.5 rounded-full bg-white px-4 text-[14px] font-semibold ring-1 ring-soil-dark/15 hover:bg-[#f5f7f1]">
            <Download className="w-3.5 h-3.5" /> The week as a file
          </a>
        ) : (
          <p className="text-[13px] text-soil-dark/70">Your supervisor files the week.</p>
        )}
      </div>
      <div className="mt-4 grid gap-5 sm:grid-cols-3">
        {items.map(({ label, s }) => {
          const top = Math.max(1, ...s.series)
          const up = (s.change_pct ?? 0) > 0
          return (
            <div key={label}>
              <p className="text-[14px] font-medium text-soil-dark/75">{label}</p>
              <p className="mt-1 flex items-baseline gap-2">
                <span className="text-[28px] font-semibold tabular-nums">{s.this_week}</span>
                {s.change_pct != null && (
                  <span className={`text-[13px] font-medium ${up ? 'text-ember' : 'text-leaf-deep'}`}>
                    {up ? '+' : ''}{s.change_pct}% on last week
                  </span>
                )}
              </p>
              <div className="mt-2 flex items-end gap-[3px] h-10" aria-hidden>
                {s.series.map((n, i) => (
                  <span key={i} className={`flex-1 rounded-[3px] ${i >= s.series.length / 2 ? 'bg-[#2f6a39]' : 'bg-[#2f6a39]/20'}`}
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
  ember: 'bg-[#f9dcd5] text-[#b5381c]',
  ochre: 'bg-[#fbe5bd] text-[#9a6210]',
  leaf: 'bg-[#d6ebcd] text-[#2f6a39]',
}

/** One thing that needs a person: what, how bad, and the way to it. */
function Row({ icon: Icon, tone, title, sub, to, action }: {
  icon: typeof AlertTriangle; tone: keyof typeof TONES; title: string; sub: string; to?: string; action?: React.ReactNode
}) {
  const body = (
    <>
      <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${TONES[tone]}`}>
        <Icon className="h-5 w-5" aria-hidden />
      </span>
      <span className="min-w-[10rem] flex-1">
        <span className="block text-[15px] font-semibold">{title}</span>
        <span className="block text-[13px] text-soil-dark/70">{sub}</span>
      </span>
      {action ?? (to
        ? <ArrowRight className="h-5 w-5 shrink-0 text-soil-dark/70 transition-transform group-hover:translate-x-0.5" aria-hidden />
        : <CheckCircle2 className="h-5 w-5 shrink-0 text-[#4b8b3b]" aria-label="Clear" />)}
    </>
  )
  const cls = 'group flex flex-wrap items-center gap-3 rounded-2xl bg-[#f8f6f0] p-3 transition-colors'
  return (
    <li>
      {to ? <Link to={to} className={`${cls} hover:bg-[#f1ede2]`}>{body}</Link> : <div className={cls}>{body}</div>}
    </li>
  )
}
