import { useState, type ReactNode } from 'react'
import {
  Activity, BrainCircuit, CalendarRange, FlaskConical, Gauge, Megaphone, PhoneCall, Loader2, RefreshCw, ShieldCheck, Stethoscope, Target, TriangleAlert, Users,
} from 'lucide-react'
import { api } from '../api/client'
import type { KccPanel as KccData, ModelCard, OutlookRow, PesticideBaseline, Summary } from '../api/types'
import { useAsync } from '../lib/hooks'
import { useAuth } from '../auth/AuthContext'
import { Link } from 'react-router-dom'
import { Bone, BoneLines, Card, ErrorBox, Loading, Pill } from '../ui/kit'

export const pct = (n: number | null | undefined, d = 0) => (n == null ? '—' : `${(n * 100).toFixed(d)}%`)

/** "1 farm", "2 farms". The console counts farms, cases and officers all over,
 *  and a district screen that says "1 farms" reads as unfinished to the person
 *  whose district it is. */
export const many = (n: number, one: string, more = `${one}s`) => `${n} ${n === 1 ? one : more}`

/** "rice_brown_planthopper" under crop "rice" → "Brown planthopper". The id
 *  already names the crop, and repeating it is what pushed these names past
 *  the edge of the card. */
export function targetName(target: string, crop?: string) {
  const bare = crop && target.startsWith(`${crop}_`) ? target.slice(crop.length + 1) : target
  const words = bare.replace(/_/g, ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/** The knowledge base has no display name for "healthy", so those labels
 *  came through raw — "maize_healthy" on a screen a district office reads. */
export function labelName(modelLabel: string, name?: string) {
  if (name && name !== modelLabel) return name
  const healthy = modelLabel.match(/^([a-z]+)_healthy$/)
  return healthy ? `Healthy ${healthy[1]}` : targetName(modelLabel)
}

/** "24 Oct". The year is noise on a list that is all this season. */
export const shortDate = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }) : '—'

/** The heading every console card opens with, so they read as one family:
 *  an icon in its own tone, a title, one sentence on what the card is for,
 *  and anything that belongs at the right of the title. */
export function CardHead({ icon: Icon, title, sub, tone = 'text-leaf', aside }: {
  icon: typeof Gauge; title: string; sub?: ReactNode; tone?: string; aside?: ReactNode
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="flex min-w-0 items-start gap-3">
        <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#eef3e6] ${tone}`}>
          <Icon className="h-5 w-5" aria-hidden />
        </span>
        <div className="min-w-0">
          <h2 className="text-[18px] font-semibold leading-tight tracking-tight">{title}</h2>
          {sub && <p className="mt-1 text-[13px] leading-relaxed text-soil-dark/70 text-pretty">{sub}</p>}
        </div>
      </div>
      {aside}
    </div>
  )
}

export function OfficerLoadPanel() {
  const { me } = useAuth()
  // Who is carrying what is the office's view. An ordinary officer is not
  // shown it and does not ask for it: the server would refuse, and a panel
  // that renders an error where a colleague's name used to be is worse than
  // no panel.
  const boss = me?.profile?.supervisor === true
  const w = useAsync(() => (boss ? api.workload() : Promise.resolve(null)), [boss])
  const [busy, setBusy] = useState(false)
  const [said, setSaid] = useState<string | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  // Routing a district's backlog is a supervisor's call. The button used to be
  // offered to every officer and refused by the server on press, with nothing
  // caught and nothing shown, so it read as a dead control.
  const mayRoute = me?.profile?.supervisor === true

  const route = async () => {
    setBusy(true)
    setFailed(null)
    setSaid(null)
    try {
      const r = await api.routeCases()
      setSaid(r.assigned === 0
        ? 'Nothing waiting to be routed.'
        : `${r.assigned} case${r.assigned === 1 ? '' : 's'} routed to the freest officers.`)
      w.reload()
    } catch (e) {
      setFailed(e instanceof Error ? e.message : 'Could not route the cases just now.')
    } finally {
      setBusy(false)
    }
  }

  if (w.error) return <Card className="p-4"><ErrorBox error={w.error} onRetry={w.reload} /></Card>
  if (!w.data) return <PanelBone rows={5} />
  // A district office cares about the desks carrying work, longest wait first.
  // Eighty idle names below them is not information.
  const officers = w.data.officers
  const carrying = officers
    .filter((o) => o.open_cases > 0)
    .sort((a, b) => b.open_cases - a.open_cases || (b.oldest_wait_hours ?? 0) - (a.oldest_wait_hours ?? 0))
    .slice(0, 8)
  const idle = officers.length - officers.filter((o) => o.open_cases > 0).length
  const busiest = Math.max(1, ...carrying.map((o) => o.open_cases))
  const districts = new Set(officers.flatMap((o) => o.districts)).size

  if (!boss) return null

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-[18px] font-semibold tracking-tight"><Users className="w-4 h-4 text-leaf" /> District officers</h2>
        <span className="text-[13px] text-soil-dark/70">
          {many(officers.length, 'officer')} · {many(districts, 'district')} · {w.data.open_total} open
        </span>
      </div>

      {officers.length === 0 ? (
        <p className="mt-3 text-sm text-soil-dark/70">
          No verified officer yet. Cases stay in everyone's queue until the district office verifies one.
        </p>
      ) : carrying.length === 0 ? (
        <p className="mt-3 text-sm text-soil-dark/70">Every desk is clear — no case is waiting on a person.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {carrying.map((o) => (
            <li key={o.user_id} className="flex items-center gap-3">
              <span className="w-40 shrink-0 truncate text-sm">
                {o.name}
                <span className="block text-[12px] text-soil-dark/70 truncate">
                  {o.districts.length > 2 ? `${o.districts.slice(0, 2).join(', ')} +${o.districts.length - 2}` : (o.districts.join(', ') || 'no district')}
                </span>
              </span>
              <span className="flex-1 h-2.5 rounded-full bg-soil-dark/10 overflow-hidden" role="img"
                aria-label={`${o.open_cases} open cases`}>
                <span className={`block h-full rounded-full ${o.open_cases >= busiest && busiest > 1 ? 'bg-ember' : 'bg-leaf'}`}
                  style={{ width: `${(o.open_cases / busiest) * 100}%` }} />
              </span>
              <span className="w-24 shrink-0 text-right text-[13px] tabular-nums text-soil-dark/70">
                {o.open_cases} open
                {o.oldest_wait_hours != null && (
                  <span className={`block ${o.oldest_wait_hours > 24 ? 'text-ember' : 'text-soil-dark/70'}`}>
                    {o.oldest_wait_hours < 1 ? 'under an hour' : `${Math.round(o.oldest_wait_hours)} h waiting`}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}

      {idle > 0 && carrying.length > 0 && (
        <p className="mt-3 text-[13px] text-soil-dark/70">
          {idle} other officer{idle === 1 ? '' : 's'} holding nothing.
        </p>
      )}

      {w.data.unassigned > 0 && (mayRoute ? (
        <button onClick={route} disabled={busy}
          className="mt-4 w-full min-h-[44px] rounded-full bg-[#1d4a2c] text-white text-sm font-medium flex items-center justify-center gap-2 disabled:opacity-60">
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
          Route {w.data.unassigned} waiting case{w.data.unassigned === 1 ? '' : 's'}
        </button>
      ) : (
        <p className="mt-4 text-[13px] text-soil-dark/70">
          {w.data.unassigned} case{w.data.unassigned === 1 ? '' : 's'} waiting to be routed. Your supervisor
          — the Agriculture Officer or the KVK scientist — places these.
        </p>
      ))}
      {said && <p className="mt-2 text-[13px] text-leaf-deep">{said}</p>}
      {failed && <p className="mt-2 text-[13px] text-ember">{failed}</p>}
    </Card>
  )
}

/** The panels the officer pages are built from. Each one fetches what it
 *  needs, so a page is a choice of panels rather than one giant loader. */
/** A panel while it loads, when it cannot load, and once it has.
 *
 *  The middle case is the one that kept going missing. useAsync stops loading
 *  and sets `error`, but a panel that only asks "is there data yet?" never
 *  reads it — so a failed call leaves its skeleton shimmering on the console for
 *  ever, with nothing for the officer to press and no sign anything is wrong.
 *  Stale data is kept on screen if a refresh fails; a first load that fails has
 *  nothing to keep, and says so. */
export function Panel<T>({ q, rows = 4, children }: {
  q: { data: T | null; error: Error | null; reload: () => void }
  rows?: number
  children: (data: T) => ReactNode
}) {
  if (q.data) return <>{children(q.data)}</>
  if (q.error) {
    return <Card className="p-5 lg:p-6"><ErrorBox error={q.error} onRetry={q.reload} /></Card>
  }
  return <PanelBone rows={rows} />
}

export function PanelBone({ rows = 4 }: { rows?: number }) {
  return (
    <Card className="p-4 space-y-3">
      <Bone className="h-4 w-40" />
      <BoneLines lines={rows} />
    </Card>
  )
}

export function KpisSkeleton() {
  return (
    <Loading label="Loading the district summary">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {Array.from({ length: 4 }, (_, i) => (
          <Card key={i} className="p-4">
            <Bone className="w-4 h-4 rounded-md" />
            <Bone className="h-8 w-16 mt-2" />
            <Bone className="h-3 w-24 mt-2 rounded-full" />
            <Bone className="h-2.5 w-20 mt-1.5 rounded-full" />
          </Card>
        ))}
      </div>
    </Loading>
  )
}

export function MapSkeleton() {
  return (
    <Loading label="Loading the hotspot map" className="h-full">
      <div className="relative h-full w-full overflow-hidden rounded-xl bg-soil-dark/[0.06] motion-safe:animate-pulse">
        {/* Where the pins will be, so the card does not read as broken. */}
        {[['28%', '34%'], ['52%', '58%'], ['68%', '30%'], ['40%', '72%']].map(([top, left]) => (
          <span key={top + left} className="absolute w-3 h-3 rounded-full bg-soil-dark/15" style={{ top, left }} />
        ))}
      </div>
    </Loading>
  )
}

export function Legend({ color, label, hollow }: { color: string; label: string; hollow?: boolean }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="w-3 h-3 rounded-full" style={hollow ? { border: `1.5px dashed ${color}` } : { background: color }} />
      {label}
    </span>
  )
}

/** A number that is only a number is a poster. Each tile is the way into the
 *  queue it counts. */
/** The one line that says which screen this is and what it is for. The console
 *  used to open cold on a card with a small bold heading, so every page looked
 *  like the middle of something. */
export function PageHead({ title, purpose, children }: {
  title: string; purpose: string; children?: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-3">
      <div className="min-w-0">
        <h1 className="font-instrument-serif text-[36px] leading-none text-[#1d3a24] lg:text-[44px]">{title}</h1>
        <p className="mt-2 max-w-3xl text-[15px] text-soil-dark/75 text-pretty">{purpose}</p>
      </div>
      {children}
    </div>
  )
}

const MONTH = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** Ten years of chemical pesticide in this state, as one column per year.
 *
 *  This used to overflow upwards into its own paragraph. The bars sat in a box
 *  80px tall while a bar alone could be 96, with a value above it and a year
 *  below, so every column was half again as tall as its container and spilled
 *  over the sentence it was meant to illustrate. The plot now has a height of
 *  its own and every bar is a share of it, so it cannot leave the box.
 *
 *  It also printed a value over all ten bars, which nobody reads. The latest
 *  year is the one that matters and is in the headline; the chart labels that
 *  and the peak, and any other year is a hover away. */
export function PesticidePanel({ p }: { p: PesticideBaseline }) {
  const [hover, setHover] = useState<number | null>(null)
  const series = p.chemical
  if (series.length === 0) return null
  const last = series.length - 1
  const peak = series.reduce((best, [, v], i) => (v > series[best][1] ? i : best), 0)
  const step = 4000
  const top = Math.max(step, Math.ceil(series[peak][1] / step) * step)
  const ticks = Array.from({ length: top / step + 1 }, (_, i) => i * step)
  const tonnes = (v: number) => Math.round(v).toLocaleString('en-IN')
  const compact = (v: number) => (v === 0 ? '0' : `${v / 1000}k`)
  const shown = hover ?? last
  // Two labels at most, and never on neighbouring columns.
  const labelled = new Set([shown, ...(Math.abs(peak - shown) > 1 ? [peak] : [])])

  return (
    <Card className="p-5 lg:p-6 h-full">
      <CardHead icon={FlaskConical} tone="text-ember" title={`Pesticide use — ${p.state}`}
        sub={<>The number &ldquo;more targeted pesticide use&rdquo; has to move.</>} />

      <div className="mt-4 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <p className="text-[28px] font-semibold tabular-nums leading-none">
          {tonnes(series[last][1])}<span className="text-base font-medium text-soil-dark/70"> t</span>
        </p>
        <p className="text-[13px] text-soil-dark/70">
          chemical pesticide in {series[last][0]}
          {p.latest_share_pct != null && <> · <b className="font-semibold text-soil-dark/80">{p.latest_share_pct}%</b> of India</>}
          {p.rank != null && <> · <b className="font-semibold text-soil-dark/80">#{p.rank}</b> of {p.states_ranked} states</>}
        </p>
      </div>

      <div className="mt-6 flex gap-2" role="img"
        aria-label={`Chemical pesticide use in ${p.state}, ${series[0][0]} to ${series[last][0]}: `
          + series.map(([y, v]) => `${y} ${tonnes(v)} tonnes`).join(', ')}>
        <div className="relative w-7 shrink-0 h-36" aria-hidden>
          {ticks.map((t) => (
            <span key={t} className="absolute right-0 translate-y-1/2 text-[12px] tabular-nums text-soil-dark/70"
              style={{ bottom: `${(t / top) * 100}%` }}>{compact(t)}</span>
          ))}
        </div>
        <div className="relative flex-1 h-36" onMouseLeave={() => setHover(null)}>
          {ticks.map((t) => (
            <span key={t} aria-hidden
              className={`absolute inset-x-0 h-px ${t === 0 ? 'bg-soil-dark/25' : 'bg-soil-dark/[0.07]'}`}
              style={{ bottom: `${(t / top) * 100}%` }} />
          ))}
          <div className="absolute inset-0 grid" style={{ gridTemplateColumns: `repeat(${series.length}, minmax(0, 1fr))` }}>
            {series.map(([year, v], i) => {
              const h = (v / top) * 100
              const accent = i === shown
              return (
                <button key={year} type="button" onMouseEnter={() => setHover(i)} onFocus={() => setHover(i)}
                  onBlur={() => setHover(null)}
                  aria-label={`${year}: ${tonnes(v)} tonnes`}
                  className="relative h-full outline-none focus-visible:bg-soil-dark/[0.04] rounded">
                  {labelled.has(i) && (
                    <span className="absolute left-1/2 -translate-x-1/2 whitespace-nowrap text-[12px] font-semibold tabular-nums text-soil-dark"
                      style={{ bottom: `calc(${h}% + 4px)` }}>
                      {compact(Math.round(v / 100) * 100)}
                    </span>
                  )}
                  <span className={`absolute bottom-0 left-1/2 -translate-x-1/2 w-[60%] max-w-[24px] rounded-t-[4px] transition-colors
                    ${accent ? 'bg-ember' : 'bg-soil-dark/15'}`}
                    style={{ height: `${h}%` }} />
                </button>
              )
            })}
          </div>
        </div>
      </div>
      <div className="mt-1.5 ml-9 grid" aria-hidden style={{ gridTemplateColumns: `repeat(${series.length}, minmax(0, 1fr))` }}>
        {series.map(([year], i) => (
          <span key={year} className={`text-center text-[12px] tabular-nums ${i === shown ? 'text-soil-dark font-medium' : 'text-soil-dark/70'}`}>
            {year.slice(2)}
          </span>
        ))}
      </div>
      <p className="mt-1 text-center text-[12px] text-soil-dark/70 tabular-nums" aria-live="polite">
        {series[shown][0]}: {tonnes(series[shown][1])} t{shown === peak ? ' · the peak' : ''}
      </p>

      <p className="mt-4 text-[13px] leading-relaxed text-soil-dark/70 text-pretty">
        AnnRakshak&apos;s lever: chemical rungs come last and collapsed, advice only above the
        confidence gate, and the spray check vetoes wrong-class, wrong-crop and herbicide sprays
        before they happen.
      </p>
      <p className="mt-3 text-[12px] leading-relaxed text-soil-dark/70">{p.source}. {p.unit_note}</p>
    </Card>
  )
}

/** What farmers actually ring the Kisan Call Centre about.
 *
 *  Fifteen years of KCC plant-protection calls, grouped by pest. It is the one
 *  independent check in the app on whether the model is trained on what
 *  farmers are actually worried about, and it had been built end to end —
 *  pipeline, knowledge-base file, service, endpoint, typed client — and shown
 *  on no screen at all.
 */
export function KccPanel({ k }: { k: KccData }) {
  const top = k.groups.slice(0, 6)
  const most = Math.max(1, ...top.map((g) => g.expected_this_month))
  return (
    <Card className="p-5 lg:p-6">
      <h2 className="flex items-center gap-2 text-[18px] font-semibold tracking-tight">
        <PhoneCall className="w-4 h-4 text-leaf" /> What farmers ring about in {MONTH[k.month]}
      </h2>
      <p className="text-[13px] text-soil-dark/70 mt-0.5">
        Kisan Call Centre plant-protection calls, {k.years[0]}–{k.years[1]}, as a check on the risk
        calendar: these are the months farmers themselves raised each problem. Calls are demand, not
        incidence — they also follow phone access and awareness.
      </p>
      <ul className="mt-4 space-y-3">
        {top.map((g) => (
          <li key={g.id}>
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-sm font-medium">{g.label}</span>
              <span className="text-[13px] tabular-nums text-soil-dark/70 shrink-0">
                ~{g.expected_this_month.toLocaleString('en-IN')} calls
              </span>
            </div>
            <div className="mt-1 h-1.5 rounded-full bg-soil-dark/[0.07] overflow-hidden">
              <span className="block h-full rounded-full bg-leaf/60"
                style={{ width: `${Math.max(3, (g.expected_this_month / most) * 100)}%` }} />
            </div>
            <p className="mt-1 text-[12px] text-soil-dark/70">
              {g.crop} · peaks {g.peak_months.map((m) => MONTH[m]).join(', ')}
              {g.top_districts.length > 0 && ` · most from ${g.top_districts.slice(0, 2).map((d) => d.district).join(', ')}`}
            </p>
          </li>
        ))}
      </ul>
      {k.groups.length > top.length && (
        <p className="mt-3 text-[12px] text-soil-dark/70">
          {k.groups.length - top.length} more pest groups in the same record.
        </p>
      )}
      <p className="mt-3 text-[12px] text-soil-dark/70">{k.source}</p>
    </Card>
  )
}

export function Kpis({ s }: { s: Summary }) {
  const t = s.totals
  const foundRate = t.alerts_answered ? t.alerts_found / t.alerts_answered : null
  const items = [
    { icon: Stethoscope, label: 'Photo diagnoses', value: t.diagnoses, sub: `${s.gate_outcomes.advise ?? 0} advised directly`, to: '/officer/model' },
    // Experts only see what the gate sent them — the hard cases — so this is
    // agreement on escalations, not overall accuracy. Low here = gate did its job.
    { icon: ShieldCheck, label: 'Expert agreed with AI', value: pct(t.field_accuracy), sub: `${t.confirmed} confirmed · ${t.corrected} corrected, on cases AI flagged unsure`, to: '/officer/model' },
    { icon: Activity, label: 'Cases closed', value: t.resolved_cases, sub: `${t.referred_to_lab} referred to a lab`, to: '/officer/queue' },
    { icon: TriangleAlert, label: 'Risk alerts issued', value: t.alerts_issued, sub: `${t.alerts_answered} inspected · ${pct(foundRate)} found something`, to: '/officer/advisories' },
  ]
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {items.map(({ icon: Icon, label, value, sub, to }) => (
        <Link key={label} to={to} className="group">
          <Card className="h-full p-4 transition-[transform,box-shadow] duration-200 group-hover:-translate-y-0.5 group-hover:shadow-[0_16px_30px_-18px_rgba(43,29,18,0.45)] lg:p-5">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#eef3e6] text-[#2f6a39]">
              <Icon className="h-5 w-5" aria-hidden />
            </span>
            <p className="mt-3 text-[30px] font-semibold leading-none tabular-nums">{value}</p>
            <p className="mt-1.5 text-[14px] font-semibold">{label}</p>
            <p className="mt-0.5 text-[13px] text-soil-dark/70">{sub}</p>
          </Card>
        </Link>
      ))}
    </div>
  )
}

/** Why the gate sent a photo to a person instead of answering. These are the
 *  gate's own reason codes (engine/gate.py), said the way an officer would
 *  say them; "crop mismatch (13)" on its own explains nothing. */
const REASON_LABEL: Record<string, string> = {
  CROP_MISMATCH: 'Looked like a disease of another crop',
  UNFAMILIAR_PHOTO: 'Unlike anything it was trained on',
  OUT_OF_SCOPE: 'Unlike anything it was trained on',
  BELOW_GATE: 'Leaning one way, not sure enough',
  BELOW_FLOOR: 'Too unsure to say anything',
  AMBIGUOUS_NO_CUE: 'Torn between two, no question to settle it',
  LAB_CLASS_BELOW_GATE: 'Lab-trained class, below its higher bar',
  NOT_PHOTO_DIAGNOSABLE: 'Not something a photo can settle',
  FOLLOWUP_WORSE: 'The farmer said it got worse',
  LIVE_FEW_VIEWS: 'Live call: too few clear views',
  NOT_A_CROP_PHOTO: 'Not a photo of a crop',
  LAB_CLASS_CONFIRM: 'Lab-trained class, asked to confirm',
}
const reasonLabel = (r: string) =>
  REASON_LABEL[r] ?? r.charAt(0) + r.slice(1).toLowerCase().replace(/_/g, ' ')

export function GatePanel({ s }: { s: Summary }) {
  const g = s.gate_outcomes
  const seg = [
    ['advise', 'Answered', 'bg-leaf'],
    ['clarify', 'Asked one question', 'bg-ochre'],
    ['escalate', 'Sent to an expert', 'bg-sky-600'],
    ['retake', 'Asked to retake', 'bg-soil-dark/25'],
  ] as const
  const total = seg.reduce((n, [k]) => n + (g[k] ?? 0), 0)
  const reasons = Object.entries(s.escalation_reasons).sort((a, b) => b[1] - a[1])
  const most = Math.max(1, ...reasons.map(([, n]) => n))
  const share = (n: number) => (total ? Math.round((n / total) * 100) : 0)

  return (
    <Card className="p-5 lg:p-6 h-full">
      <CardHead icon={Gauge} title="The gate, on farmers' photos"
        sub="Every photo sent so far: answered, settled with one question, handed to a person, or sent back for a better picture — instead of a guess." />
      {total === 0 ? <p className="mt-4 text-sm text-soil-dark/70">No photographs yet.</p> : (
        <>
          <p className="mt-4 text-sm">
            <b className="text-[28px] font-semibold tabular-nums leading-none">{total}</b>
            <span className="ml-2 text-soil-dark/70">photos</span>
          </p>
          {/* Two-pixel gaps rather than borders: neighbours read apart by the
              space between them, not by ink drawn around them. */}
          <div className="mt-3 flex h-2.5 gap-[2px]" role="img"
            aria-label={seg.map(([k, l]) => `${l} ${g[k] ?? 0}`).join(', ')}>
            {seg.map(([k, , cls]) => (g[k] ?? 0) > 0 && (
              <span key={k} className={`${cls} first:rounded-l-full last:rounded-r-full`}
                style={{ width: `${((g[k] ?? 0) / total) * 100}%` }} />
            ))}
          </div>
          <ul className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2">
            {seg.map(([k, l, cls]) => (
              <li key={k} className="flex items-center gap-2 text-[13px]">
                <span className={`w-2.5 h-2.5 rounded-sm shrink-0 ${cls}`} />
                <span className="min-w-0 flex-1 text-soil-dark/75">{l}</span>
                <span className="tabular-nums font-semibold">{g[k] ?? 0}</span>
                <span className="w-8 text-right tabular-nums text-soil-dark/70">{share(g[k] ?? 0)}%</span>
              </li>
            ))}
          </ul>

          {reasons.length > 0 && (
            <div className="mt-5 pt-4 border-t border-soil-dark/10">
              <h3 className="text-[14px] font-semibold text-soil-dark/85">Why it handed one over</h3>
              <ul className="mt-3 space-y-2.5">
                {reasons.map(([r, n]) => (
                  <li key={r}>
                    <div className="flex items-baseline justify-between gap-3 text-[13px]">
                      <span className="text-soil-dark/80">{reasonLabel(r)}</span>
                      <span className="tabular-nums font-semibold shrink-0">{n}</span>
                    </div>
                    <div className="mt-1 h-1.5 rounded-full bg-soil-dark/[0.06]">
                      <span className="block h-full rounded-full bg-sky-600/70" style={{ width: `${(n / most) * 100}%` }} />
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </Card>
  )
}

export function ModelPanel({ m }: { m: ModelCard }) {
  if (m.is_stub) {
    return (
      <Card className="p-5 lg:p-6 h-full border-ochre/40">
        <CardHead icon={BrainCircuit} tone="text-ochre" title="Vision model"
          sub={<>Running the labelled demo stub — train with <code>ml/train.py</code> to load the ICAR model.</>} />
      </Card>
    )
  }
  const g = m.gate_on_test
  const t = m.test
  const best = m.benchmark?.reduce((a, b) => (b.accuracy > a.accuracy ? b : a))
  const trained = m.trained_at ? new Date(m.trained_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : null

  return (
    <Card className="p-5 lg:p-6 h-full">
      <CardHead icon={BrainCircuit} title="The model, on photos it has never seen"
        sub={<>Scored on {m.split?.test ?? '—'} held-out ICAR photographs, kept out of training entirely.
          {m.classes?.length ? <> It knows {m.classes.length} problems across the four crops.</> : null}</>}
        aside={<Pill tone="leaf" className="shrink-0">{(m.backbone ?? '').replace(/_/g, ' ')}{m.head === 'finetune' ? ' · fine-tuned' : ''}</Pill>} />

      {/* The headline is the gate's number, not top-1: an answer is only ever
          given above the gate, so "how often is it right when it speaks" is the
          accuracy a farmer actually meets. */}
      <div className="mt-4 grid grid-cols-2 lg:grid-cols-4 gap-2.5">
        <Figure value={pct(g?.accuracy_when_advised, 1)} label="right when it answers" strong />
        <Figure value={g ? `${g.advise_pct}%` : '—'} label="answered directly"
          sub={g ? `${g.escalate_pct}% to an expert` : undefined} />
        <Figure value={pct(t?.accuracy, 1)} label="top-1 accuracy" sub={t ? `macro-F1 ${t.f1.toFixed(2)}` : undefined} />
        <Figure value={t ? t.ece_after.toFixed(3) : '—'} label="calibration error"
          sub={t ? `${t.ece_before.toFixed(3)} before scaling` : undefined} />
      </div>

      {m.benchmark && m.benchmark.length > 0 && (
        <div className="mt-5">
          <h3 className="text-[14px] font-semibold text-soil-dark/85">Approaches compared on the ICAR test set</h3>
          <table className="mt-2 w-full text-[13px]">
            <thead className="text-soil-dark/70">
              <tr>
                <th className="text-left font-medium py-1.5">Approach</th>
                <th className="text-right font-medium w-16">Accuracy</th>
                <th className="text-right font-medium w-14">F1</th>
              </tr>
            </thead>
            <tbody>
              {m.benchmark.map((b) => {
                const ours = b === best
                return (
                  <tr key={b.model} className={`border-t border-soil-dark/[0.07] ${ours ? 'font-semibold' : 'text-soil-dark/75'}`}>
                    <td className="py-1.5 pr-2">
                      {b.model.replace(/_/g, ' ')}
                      {ours && <Pill tone="leaf" className="ml-2 !py-0.5">best</Pill>}
                    </td>
                    <td className="text-right tabular-nums">{(b.accuracy * 100).toFixed(1)}%</td>
                    <td className="text-right tabular-nums">{b.f1.toFixed(3)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <details className="mt-4 group text-[12px] text-soil-dark/70">
        <summary className="cursor-pointer select-none hover:text-soil-dark/80">
          What it was trained on{trained ? ` · trained ${trained}` : ''}
        </summary>
        <p className="mt-2 leading-relaxed">{m.dataset}</p>
        {m.split && (
          <p className="mt-1 tabular-nums">
            {m.split.train.toLocaleString('en-IN')} training · {m.split.val.toLocaleString('en-IN')} validation · {m.split.test} test photographs
          </p>
        )}
        <p className="mt-1 break-all text-soil-dark/70">{m.model_version}</p>
      </details>
    </Card>
  )
}

/** One headline number. The console's stat tiles read value, then what it
 *  is, then the one qualifier that keeps it honest. */
function Figure({ value, label, sub, strong }: { value: string; label: string; sub?: string; strong?: boolean }) {
  return (
    <div className={`rounded-2xl px-4 py-3.5 ${strong ? 'bg-[#e3efd9] ring-1 ring-[#4b8b3b]/20' : 'bg-[#fdf5e6]'}`}>
      <p className={`text-[26px] font-semibold tabular-nums leading-none ${strong ? 'text-[#2f6a39]' : 'text-[#7a4f12]'}`}>{value}</p>
      <p className="mt-1.5 text-[12px] font-medium leading-tight text-soil-dark/75">{label}</p>
      {sub && <p className="mt-0.5 text-[12px] leading-tight text-soil-dark/70 tabular-nums">{sub}</p>}
    </div>
  )
}

export function Stat({ v, l, strong }: { v: string; l: string; strong?: boolean }) {
  return (
    <div className={`rounded-xl p-2.5 ${strong ? 'bg-[#e3efd9]' : 'bg-[#f8f6f0]'}`}>
      <p className={`text-xl font-semibold ${strong ? 'text-leaf-deep' : ''}`}>{v}</p>
      <p className="text-[12px] text-soil-dark/70 leading-tight">{l}</p>
    </div>
  )
}

export function DistrictTable({ s }: { s: Summary }) {
  return (
    <Card className="p-5 lg:p-6">
      <CardHead icon={Target} title="Districts" sub="Farms, cases and this week's high alerts in each district." />
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-[14px]">
          <thead className="text-[13px] text-soil-dark/70">
            <tr className="border-b border-soil-dark/10"><th className="py-2 text-left font-semibold">District</th><th className="text-right font-semibold">Farms</th><th className="text-right font-semibold">Confirmed</th><th className="text-right font-semibold">AI-advised</th><th className="text-right font-semibold">Queue</th><th className="text-right font-semibold">High alerts</th></tr>
          </thead>
          <tbody>
            {s.by_district.map((d) => (
              <tr key={d.district} className="border-t border-soil-dark/[0.06] tabular-nums">
                <td className="py-2.5 font-medium">
                  <Link to={`/officer/queue?district=${encodeURIComponent(d.district)}`}
                    className="hover:text-leaf-deep hover:underline underline-offset-2">{d.district}</Link>
                </td>
                <td className="text-right">{d.farms}</td>
                <td className={`text-right ${d.confirmed ? 'text-ember font-semibold' : ''}`}>{d.confirmed}</td>
                <td className="text-right">{d.suspected}</td>
                <td className="text-right">{d.open_cases}</td>
                <td className={`text-right ${d.active_high_alerts ? 'text-ochre font-semibold' : ''}`}>{d.active_high_alerts}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

/** Where an expert agreed with the model and where they corrected it, per
 *  label, weakest first — the order in which the classes need photographs.
 *
 *  It was a stack of full-width bars, one per label, in the order the database
 *  returned them, so "maize_healthy" (a raw id) sat between two diseases with
 *  a thick red bar and no way to tell that it rested on a single case. */
export function AccuracyPanel({ s }: { s: Summary }) {
  const rows = s.accuracy_by_label
    .map((a) => ({ ...a, n: a.confirmed + a.corrected }))
    .filter((a) => a.n > 0)
    .sort((a, b) => a.confirmed / a.n - b.confirmed / b.n || b.n - a.n)
  return (
    <Card className="p-5 lg:p-6 h-full">
      <CardHead icon={ShieldCheck} title="Where experts corrected it"
        sub="Experts only see the cases the gate was unsure of, so this is agreement on the hard ones, not overall accuracy. Weakest first — these are the classes that need field photographs." />
      {rows.length === 0 ? <p className="mt-4 text-sm text-soil-dark/70">No expert verdicts yet.</p> : (
        <table className="mt-4 w-full text-sm">
          <thead className="text-[13px] font-semibold text-soil-dark/75">
            <tr>
              <th className="text-left font-semibold pb-2">Model said</th>
              <th className="text-right font-semibold pb-2 w-16">Agreed</th>
              <th className="text-right font-semibold pb-2 w-20">Corrected</th>
              <th className="pb-2 pl-4 w-[30%]"><span className="sr-only">Agreement</span></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => {
              const agree = a.confirmed / a.n
              return (
                <tr key={a.model_label} className="border-t border-soil-dark/[0.07]">
                  <td className="py-2 pr-2">
                    <span className="font-medium">{labelName(a.model_label, a.name)}</span>
                    {a.n === 1 && <span className="ml-1.5 text-[12px] text-soil-dark/70">one case</span>}
                  </td>
                  <td className="text-right tabular-nums text-leaf-deep">{a.confirmed}</td>
                  <td className={`text-right tabular-nums ${a.corrected ? 'text-ember font-semibold' : 'text-soil-dark/70'}`}>{a.corrected}</td>
                  <td className="pl-4">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 flex h-1.5 gap-[2px]" aria-hidden>
                        {a.confirmed > 0 && <span className="rounded-l-full last:rounded-r-full bg-leaf" style={{ width: `${agree * 100}%` }} />}
                        {a.corrected > 0 && <span className="rounded-r-full first:rounded-l-full bg-ember/80" style={{ width: `${(1 - agree) * 100}%` }} />}
                      </div>
                      <span className="w-9 text-right text-[12px] tabular-nums text-soil-dark/70">{Math.round(agree * 100)}%</span>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
      {s.top_targets.length > 0 && (
        <div className="mt-5 pt-4 border-t border-soil-dark/10">
          <h3 className="text-[14px] font-semibold text-soil-dark/85">Most reported in the field</h3>
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {s.top_targets.slice(0, 8).map((t) => (
              <span key={t.target} className="inline-flex items-center gap-1.5 rounded-full bg-soil-dark/[0.05] px-2.5 py-1 text-[12px] text-soil-dark/80">
                {t.confirmed > 0 && <span className="w-1.5 h-1.5 rounded-full bg-ember" title="confirmed by an expert" />}
                {labelName(t.target, t.name)}
                <span className="font-semibold tabular-nums">{t.confirmed + t.suspected}</span>
              </span>
            ))}
          </div>
          <p className="mt-2 text-[12px] text-soil-dark/70 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-ember" /> at least one confirmed by an expert
          </p>
        </div>
      )}
    </Card>
  )
}

const TRIGGER_LABEL: Record<string, string> = {
  weather: 'weather', 'weather+phenology': 'weather + stage', phenology: 'crop stage', trap: 'trap count', spread: 'confirmed nearby',
}

/** What is building across the district this week, one row per problem, and
 *  what to do about each.
 *
 *  It lived in the narrow column of the advisories page — seven columns in a
 *  third of the width — so the table squeezed instead of scrolling: "Farms"
 *  and "High" ran into one word, a disease name took three lines, and the
 *  inputs column was off the edge. It is full width now, and below that width
 *  it scrolls rather than crushes.
 *
 *  "High" was also the wrong word. It counts high-level alerts, not farms — a
 *  single field can carry two — so next to "Farms" it read as "high-risk
 *  farms" and said something the numbers do not. */
export function OutlookPanel({ rows, onDraft }: { rows: OutlookRow[]; onDraft?: (r: OutlookRow) => void }) {
  const shown = rows.slice(0, 10)
  return (
    <Card className="p-5 lg:p-6">
      <CardHead icon={CalendarRange} title="Risk outlook — what is building this week"
        sub="From weather, crop stage, trap counts and confirmed cases nearby. Where to send scouts, and which ICAR bio-inputs to stock — Tricho-cards need a 45-day indent, so order when the risk starts building, not when it arrives."
        aside={rows.length > 0 ? <Pill tone="neutral" className="shrink-0">{many(rows.length, 'problem')}</Pill> : undefined} />
      {rows.length === 0 ? (
        <p className="mt-4 text-sm text-soil-dark/70">Nothing is building this week — no alert has been raised in seven days.</p>
      ) : (
        <div className="mt-4 -mx-4 md:-mx-5 overflow-x-auto">
          <table className="w-full min-w-[880px] text-sm">
            <thead>
              <tr className="text-[13px] font-semibold text-soil-dark/75 whitespace-nowrap">
                <th className="text-left font-semibold py-2 pl-4 md:pl-5">Pest or disease</th>
                <th className="text-right font-semibold py-2 px-3">Farms</th>
                <th className="text-right font-semibold py-2 px-3">High alerts</th>
                <th className="text-left font-semibold py-2 px-3">Districts</th>
                <th className="text-left font-semibold py-2 px-3">Why</th>
                <th className="text-right font-semibold py-2 px-3">Checked</th>
                <th className="text-left font-semibold py-2 px-3">ICAR inputs to stock</th>
                {onDraft && <th className="py-2 pr-4 md:pr-5"><span className="sr-only">Action</span></th>}
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.target} className="border-t border-soil-dark/[0.07] align-top hover:bg-soil-dark/[0.02]">
                  <td className="py-3 pl-4 md:pl-5 pr-3">
                    <p className="font-medium leading-snug">{r.name}</p>
                    <p className="text-[12px] text-soil-dark/70 capitalize">{r.crop}</p>
                  </td>
                  <td className="py-3 px-3 text-right tabular-nums">{r.farms}</td>
                  <td className="py-3 px-3 text-right tabular-nums">
                    {r.high > 0
                      ? <span className="inline-flex items-center gap-1.5 font-semibold text-ember"><span className="w-1.5 h-1.5 rounded-full bg-ember" />{r.high}</span>
                      : <span className="text-soil-dark/70">0</span>}
                  </td>
                  <td className="py-3 px-3 text-[13px] text-soil-dark/75">{r.districts.join(', ')}</td>
                  <td className="py-3 px-3">
                    <div className="flex flex-wrap gap-1">
                      {Object.keys(r.triggers).map((k) => (
                        <span key={k} className="rounded-full bg-soil-dark/[0.05] px-2 py-0.5 text-[12px] text-soil-dark/70 whitespace-nowrap">
                          {TRIGGER_LABEL[k] ?? k}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="py-3 px-3 text-right text-[13px] tabular-nums whitespace-nowrap">
                    {r.inspected
                      ? <><span className={r.found ? 'text-ember font-semibold' : ''}>{r.found}</span><span className="text-soil-dark/70"> of {r.inspected} found it</span></>
                      : <span className="text-soil-dark/70">not yet</span>}
                  </td>
                  <td className="py-3 px-3">
                    {r.icar_inputs.length === 0 ? <span className="text-[13px] text-soil-dark/70">—</span> : (
                      <div className="flex flex-wrap gap-1 max-w-[260px]">
                        {r.icar_inputs.map((x) => (
                          <span key={x.id} title={`${x.source_name} — ${x.institute.name}, ${x.institute.city}${x.institute.phone ? `, ${x.institute.phone}` : ''}`}
                            className={`text-[12px] rounded-full px-2 py-0.5 ${x.lead_time_days ? 'bg-ochre/15 text-[#8a5a17]' : 'bg-leaf/10 text-leaf-deep'}`}>
                            {x.short}{x.lead_time_days ? ` · order ${x.lead_time_days} d ahead` : ''}
                          </span>
                        ))}
                      </div>
                    )}
                  </td>
                  {onDraft && (
                    <td className="py-2.5 pr-4 md:pr-5 text-right">
                      <button type="button" onClick={() => onDraft(r)}
                        className="whitespace-nowrap inline-flex items-center gap-1.5 min-h-[34px] px-3 rounded-full border border-leaf-deep/25 text-[13px] font-medium text-leaf-deep hover:bg-leaf-deep hover:text-cream transition-colors">
                        <Megaphone className="w-3.5 h-3.5" /> Draft advisory
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rows.length > shown.length && (
        <p className="mt-3 text-[12px] text-soil-dark/70">{rows.length - shown.length} more with lower risk this week.</p>
      )}
    </Card>
  )
}

const STAT_TONE = {
  red: { card: 'bg-[#fdf0ed]', icon: 'bg-[#f9dcd5] text-[#b5381c]' },
  amber: { card: 'bg-[#fdf5e6]', icon: 'bg-[#fbe5bd] text-[#9a6210]' },
  green: { card: 'bg-[#eef6ea]', icon: 'bg-[#d6ebcd] text-[#2f6a39]' },
  violet: { card: 'bg-[#f3f0fb]', icon: 'bg-[#e3dcf6] text-[#5b45a8]' },
} as const

/** One district number, and the screen that settles it. */
export function StatCard({ icon: Icon, tone, value, label, to }: {
  icon: typeof Gauge; tone: keyof typeof STAT_TONE; value: number | null | undefined; label: string; to?: string
}) {
  const s = STAT_TONE[tone]
  const cls = `group flex flex-col items-start gap-3 rounded-[22px] p-4 sm:flex-row sm:items-center sm:gap-3.5 shadow-[0_10px_26px_-20px_rgba(43,29,18,0.45)] ring-1 ring-soil-dark/[0.06] lg:p-5 ${s.card}`
  const body = (
    <>
      <span className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl ${s.icon}`}>
        <Icon className="h-6 w-6" aria-hidden />
      </span>
      <span className="min-w-0">
        <span className="block text-[28px] font-semibold leading-none tabular-nums">
          {value == null ? <span className="inline-block h-6 w-10 animate-pulse rounded bg-soil-dark/10" /> : value}
        </span>
        <span className="mt-1 block text-[14px] font-medium leading-snug text-soil-dark/80">{label}</span>
      </span>
    </>
  )
  return to
    ? <Link to={to} className={`${cls} transition-transform duration-200 hover:-translate-y-0.5`}>{body}</Link>
    : <div className={cls}>{body}</div>
}
