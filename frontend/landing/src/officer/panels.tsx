import { useState } from 'react'
import {
  Activity, BrainCircuit, CalendarRange, CloudRain, FlaskConical, Gauge, Loader2, RefreshCw, ShieldCheck, Stethoscope, Target, TriangleAlert, Users,
} from 'lucide-react'
import { api } from '../api/client'
import type { ModelCard, OutlookRow, PesticideBaseline, RainfallPanel, Summary } from '../api/types'
import { useAsync } from '../lib/hooks'
import { useAuth } from '../auth/AuthContext'
import { Link } from 'react-router-dom'
import { Bone, BoneLines, Card, ErrorBox, Loading, Pill } from '../ui/kit'

export const pct = (n: number | null | undefined, d = 0) => (n == null ? '—' : `${(n * 100).toFixed(d)}%`)

export function OfficerLoadPanel() {
  const w = useAsync(() => api.workload(), [])
  const { me } = useAuth()
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

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold flex items-center gap-2"><Users className="w-4 h-4 text-leaf" /> District officers</h2>
        <span className="text-xs text-soil-dark/60">
          {officers.length} officers · {districts} districts · {w.data.open_total} open
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
                <span className="block text-[11px] text-soil-dark/60 truncate">
                  {o.districts.length > 2 ? `${o.districts.slice(0, 2).join(', ')} +${o.districts.length - 2}` : (o.districts.join(', ') || 'no district')}
                </span>
              </span>
              <span className="flex-1 h-2.5 rounded-full bg-soil-dark/10 overflow-hidden" role="img"
                aria-label={`${o.open_cases} open cases`}>
                <span className={`block h-full rounded-full ${o.open_cases >= busiest && busiest > 1 ? 'bg-ember' : 'bg-leaf'}`}
                  style={{ width: `${(o.open_cases / busiest) * 100}%` }} />
              </span>
              <span className="w-24 shrink-0 text-right text-xs tabular-nums text-soil-dark/70">
                {o.open_cases} open
                {o.oldest_wait_hours != null && (
                  <span className={`block ${o.oldest_wait_hours > 24 ? 'text-ember' : 'text-soil-dark/50'}`}>
                    {o.oldest_wait_hours < 1 ? 'under an hour' : `${Math.round(o.oldest_wait_hours)} h waiting`}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}

      {idle > 0 && carrying.length > 0 && (
        <p className="mt-3 text-xs text-soil-dark/60">
          {idle} other officer{idle === 1 ? '' : 's'} holding nothing.
        </p>
      )}

      {w.data.unassigned > 0 && (mayRoute ? (
        <button onClick={route} disabled={busy}
          className="mt-4 w-full min-h-[44px] rounded-full bg-leaf-deep text-cream text-sm font-medium flex items-center justify-center gap-2 disabled:opacity-60">
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
          Route {w.data.unassigned} waiting case{w.data.unassigned === 1 ? '' : 's'}
        </button>
      ) : (
        <p className="mt-4 text-xs text-soil-dark/60">
          {w.data.unassigned} case{w.data.unassigned === 1 ? '' : 's'} waiting to be routed. Your supervisor
          — the Agriculture Officer or the KVK scientist — places these.
        </p>
      ))}
      {said && <p className="mt-2 text-xs text-leaf-deep">{said}</p>}
      {failed && <p className="mt-2 text-xs text-ember">{failed}</p>}
    </Card>
  )
}

/** The panels the officer pages are built from. Each one fetches what it
 *  needs, so a page is a choice of panels rather than one giant loader. */
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
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {Array.from({ length: 5 }, (_, i) => (
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
export function Kpis({ s }: { s: Summary }) {
  const t = s.totals
  const foundRate = t.alerts_answered ? t.alerts_found / t.alerts_answered : null
  const items = [
    { icon: Users, label: 'Farms monitored', value: t.farms, sub: `${s.by_district.length} districts`, to: '/officer/map' },
    { icon: Stethoscope, label: 'Photo diagnoses', value: t.diagnoses, sub: `${s.gate_outcomes.advise ?? 0} advised directly`, to: '/officer/model' },
    // Experts only see what the gate sent them — the hard cases — so this is
    // agreement on escalations, not overall accuracy. Low here = gate did its job.
    { icon: ShieldCheck, label: 'Expert agreed with AI', value: pct(t.field_accuracy), sub: `${t.confirmed} confirmed · ${t.corrected} corrected, on cases AI flagged unsure`, to: '/officer/model' },
    { icon: Activity, label: 'Expert queue', value: t.open_cases, sub: `${t.resolved_cases} resolved · ${t.referred_to_lab} to lab`, to: '/officer/queue' },
    { icon: TriangleAlert, label: 'Risk alerts issued', value: t.alerts_issued, sub: `${t.alerts_answered} inspected · ${pct(foundRate)} found something`, to: '/officer/advisories' },
  ]
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
      {items.map(({ icon: Icon, label, value, sub, to }) => (
        <Link key={label} to={to} className="group">
          <Card className="p-4 h-full transition-colors group-hover:border-leaf/40 group-hover:bg-leaf/[0.03]">
            <Icon className="w-4 h-4 text-leaf" />
            <p className="mt-2 text-3xl font-semibold leading-none">{value}</p>
            <p className="mt-1 text-xs font-medium">{label}</p>
            <p className="text-[11px] text-soil-dark/60 mt-0.5">{sub}</p>
          </Card>
        </Link>
      ))}
    </div>
  )
}

export function GatePanel({ s }: { s: Summary }) {
  const g = s.gate_outcomes
  const total = (g.advise ?? 0) + (g.clarify ?? 0) + (g.escalate ?? 0) + (g.retake ?? 0)
  const seg = [
    ['advise', 'Advised', 'bg-leaf'],
    ['clarify', 'Asked one question', 'bg-ochre'],
    ['escalate', 'Sent to expert', 'bg-sky-600'],
    ['retake', 'Asked for retake', 'bg-soil-dark/30'],
  ] as const
  const reasons = Object.entries(s.escalation_reasons).sort((a, b) => b[1] - a[1])
  return (
    <Card className="p-4">
      <h2 className="font-semibold flex items-center gap-2"><Gauge className="w-4 h-4 text-leaf" /> Confidence gate</h2>
      <p className="text-xs text-soil-dark/60 mt-0.5">How often the system answered, asked, or admitted it wasn't sure — instead of guessing.</p>
      {total === 0 ? <p className="mt-3 text-sm text-soil-dark/50">No diagnoses yet.</p> : (
        <>
          <div className="mt-3 flex h-3 rounded-full overflow-hidden">
            {seg.map(([k, , cls]) => (g[k] ?? 0) > 0 && <div key={k} className={cls} style={{ width: `${((g[k] ?? 0) / total) * 100}%` }} />)}
          </div>
          <ul className="mt-2 grid grid-cols-2 gap-1 text-xs">
            {seg.map(([k, l, cls]) => (
              <li key={k} className="flex items-center gap-1.5"><span className={`w-2 h-2 rounded-full ${cls}`} />{l}: <b>{g[k] ?? 0}</b></li>
            ))}
          </ul>
          {reasons.length > 0 && (
            <p className="mt-2 text-[11px] text-soil-dark/50">Escalations: {reasons.map(([r, n]) => `${r.toLowerCase().replace(/_/g, ' ')} (${n})`).join(', ')}</p>
          )}
        </>
      )}
    </Card>
  )
}

export function ModelPanel({ m }: { m: ModelCard }) {
  if (m.is_stub) {
    return (
      <Card className="p-4 border-ochre/40">
        <h2 className="font-semibold flex items-center gap-2"><BrainCircuit className="w-4 h-4 text-ochre" /> Vision model</h2>
        <p className="mt-2 text-sm text-soil-dark/70">Running the labelled demo stub — train with <code>ml/train.py</code> to load the ICAR model.</p>
      </Card>
    )
  }
  const g = m.gate_on_test!
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold flex items-center gap-2"><BrainCircuit className="w-4 h-4 text-leaf" /> Vision model</h2>
        <Pill tone="leaf">{m.backbone} · {m.head}</Pill>
      </div>
      <p className="text-[11px] text-soil-dark/50 mt-0.5">{m.dataset} · test set {m.split?.test} images, never seen in training</p>
      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
        <Stat v={pct(m.test?.accuracy, 1)} l="Top-1 accuracy" />
        <Stat v={pct(g.accuracy_when_advised, 1)} l="Accuracy when it advises" strong />
        <Stat v={`${g.advise_pct}%`} l="Advised directly" />
      </div>
      <p className="mt-2 text-[11px] text-soil-dark/60">Macro-F1 {m.test?.f1.toFixed(3)} · calibration error {m.test?.ece_before.toFixed(3)} → {m.test?.ece_after.toFixed(3)} after temperature scaling · {g.clarify_pct}% asked a question, {g.escalate_pct}% escalated.</p>
      {m.benchmark && (
        <table className="mt-3 w-full text-[11px]">
          <thead className="text-soil-dark/50"><tr><th className="text-left font-medium">Approach (paper)</th><th className="text-right font-medium">Test acc</th><th className="text-right font-medium">F1</th></tr></thead>
          <tbody>
            {m.benchmark.map((b) => (
              <tr key={b.model} className="border-t border-soil-dark/5">
                <td className="py-1">{b.model}</td>
                <td className="text-right">{(b.accuracy * 100).toFixed(1)}%</td>
                <td className="text-right">{b.f1.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  )
}

export function Stat({ v, l, strong }: { v: string; l: string; strong?: boolean }) {
  return (
    <div className={`rounded-xl p-2 ${strong ? 'bg-leaf/10' : 'bg-cream'}`}>
      <p className={`text-xl font-semibold ${strong ? 'text-leaf-deep' : ''}`}>{v}</p>
      <p className="text-[10px] text-soil-dark/60 leading-tight">{l}</p>
    </div>
  )
}

export function DistrictTable({ s }: { s: Summary }) {
  return (
    <Card className="p-4">
      <h2 className="font-semibold flex items-center gap-2"><Target className="w-4 h-4 text-leaf" /> Districts</h2>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-soil-dark/50">
            <tr><th className="text-left font-medium py-1">District</th><th className="text-right font-medium">Farms</th><th className="text-right font-medium">Confirmed</th><th className="text-right font-medium">AI-advised</th><th className="text-right font-medium">Queue</th><th className="text-right font-medium">High alerts</th></tr>
          </thead>
          <tbody>
            {s.by_district.map((d) => (
              <tr key={d.district} className="border-t border-soil-dark/5">
                <td className="py-1.5">
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

export function AccuracyPanel({ s }: { s: Summary }) {
  return (
    <Card className="p-4">
      <h2 className="font-semibold flex items-center gap-2"><ShieldCheck className="w-4 h-4 text-leaf" /> Learning from field confirmations</h2>
      <p className="text-xs text-soil-dark/60 mt-0.5">Every expert verdict is a labelled field record. Confirmed-vs-corrected per model label shows where the model is weak in the field; the counts also nudge (capped) the district prior.</p>
      {s.accuracy_by_label.length === 0 ? <p className="mt-3 text-sm text-soil-dark/50">No expert verdicts yet.</p> : (
        <ul className="mt-3 space-y-2">
          {s.accuracy_by_label.map((a) => {
            const n = a.confirmed + a.corrected
            return (
              <li key={a.model_label}>
                <div className="flex justify-between text-sm"><span>{a.name}</span><span className="text-soil-dark/60 text-xs">{a.confirmed}/{n} confirmed</span></div>
                <div className="mt-1 flex h-2 rounded-full overflow-hidden bg-soil-dark/10">
                  <div className="bg-leaf" style={{ width: `${(a.confirmed / n) * 100}%` }} />
                  <div className="bg-ember" style={{ width: `${(a.corrected / n) * 100}%` }} />
                </div>
              </li>
            )
          })}
        </ul>
      )}
      {s.top_targets.length > 0 && (
        <>
          <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-soil-dark/50">Most reported</h3>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {s.top_targets.slice(0, 8).map((t) => (
              <Pill key={t.target} tone={t.confirmed ? 'ember' : 'ochre'}>{t.name} · {t.confirmed + t.suspected}</Pill>
            ))}
          </div>
        </>
      )}
    </Card>
  )
}

export function Sparkline({ series }: { series: [number, number | null, number | null][] }) {
  const pts = series.filter((s) => s[2] != null).slice(-60)
  if (pts.length < 2) return null
  const w = 260, h = 56
  const max = Math.max(...pts.map((p) => Math.abs(p[2]!)), 1)
  const x = (i: number) => (i / (pts.length - 1)) * w
  const y = (v: number) => h / 2 - (v / max) * (h / 2 - 2)
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-14" role="img" aria-label="Monsoon rainfall departure by year">
      <line x1="0" x2={w} y1={h / 2} y2={h / 2} stroke="currentColor" strokeOpacity="0.15" />
      {pts.map((p, i) => (
        <rect key={p[0]} x={x(i) - 1.5} width="3" y={Math.min(y(p[2]!), h / 2)} height={Math.abs(y(p[2]!) - h / 2)}
          fill={p[2]! >= 0 ? '#2f6fa8' : '#c8862d'} opacity="0.8">
          <title>{p[0]}: {p[2]! > 0 ? '+' : ''}{p[2]}%</title>
        </rect>
      ))}
    </svg>
  )
}

export function RainfallSection({ r }: { r: RainfallPanel }) {
  return (
    <Card className="p-4">
      <h2 className="font-semibold flex items-center gap-2"><CloudRain className="w-4 h-4 text-leaf" /> Rainfall against the IMD normal</h2>
      <p className="text-xs text-soil-dark/60 mt-0.5">This month so far (observed) against each subdivision's 1901–2015 IMD normal, and the last 60 monsoons' departure from normal. Abnormal rain shifts disease and pest risk — the risk engine reads the same numbers.</p>
      <div className="mt-4 grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {r.subdivisions.map((s) => {
          const c = s.current_month
          const dep = c?.departure_pct
          return (
            <div key={s.subdivision} className="rounded-xl bg-cream p-3">
              <p className="text-sm font-semibold">{s.subdivision.replace('&', 'and')}</p>
              <p className="text-[11px] text-soil-dark/50">ref: {s.reference_place} · JJAS normal {Math.round(s.jjas_normal_mm)} mm</p>
              <div className="mt-2 flex items-baseline gap-2">
                <span className={`text-2xl font-semibold ${dep == null ? '' : dep > 25 ? 'text-sky-700' : dep < -25 ? 'text-[#8a5a17]' : 'text-leaf-deep'}`}>
                  {dep == null ? '—' : `${dep > 0 ? '+' : ''}${dep}%`}
                </span>
                <span className="text-[11px] text-soil-dark/60">{c?.observed_mm != null ? `${c.observed_mm} mm vs ${c.expected_to_date_mm} mm normal to date` : 'no observation'}</span>
              </div>
              <div className="text-soil-dark"><Sparkline series={s.jjas_series} /></div>
            </div>
          )
        })}
      </div>
      <p className="mt-2 text-[10px] text-soil-dark/40">{r.source}</p>
    </Card>
  )
}

const TRIGGER_LABEL: Record<string, string> = {
  weather: 'weather', 'weather+phenology': 'weather + stage', phenology: 'crop stage', trap: 'trap count', spread: 'confirmed nearby',
}

export function OutlookPanel({ rows }: { rows: OutlookRow[] }) {
  return (
    <Card className="p-4">
      <h2 className="font-semibold flex items-center gap-2"><CalendarRange className="w-4 h-4 text-leaf" /> Risk outlook — plan preventive action</h2>
      <p className="text-xs text-soil-dark/60 mt-0.5">Pests and diseases building this week, from weather, crop stage, trap counts and confirmed nearby cases. Where to send scouts, and which ICAR bio-inputs to stock — Tricho-cards need a 45-day indent, so order when the risk starts building.</p>
      {rows.length === 0 ? <p className="mt-3 text-sm text-soil-dark/50">No active risk this week.</p> : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-soil-dark/50">
              <tr><th className="text-left font-medium py-1">Pest / disease</th><th className="text-right font-medium">Farms</th><th className="text-right font-medium">High</th><th className="text-left font-medium pl-3">Districts</th><th className="text-left font-medium pl-3">Driven by</th><th className="text-right font-medium">Found on check</th><th className="text-left font-medium pl-3">ICAR inputs to stock</th></tr>
            </thead>
            <tbody>
              {rows.slice(0, 10).map((r) => (
                <tr key={r.target} className="border-t border-soil-dark/5 align-top">
                  <td className="py-1.5"><span className="font-medium">{r.name}</span> <span className="text-[11px] text-soil-dark/50">{r.crop}</span></td>
                  <td className="text-right">{r.farms}</td>
                  <td className={`text-right ${r.high ? 'text-ember font-semibold' : ''}`}>{r.high}</td>
                  <td className="pl-3 text-xs text-soil-dark/70">{r.districts.join(', ')}</td>
                  <td className="pl-3 text-xs text-soil-dark/70">{Object.keys(r.triggers).map((k) => TRIGGER_LABEL[k] ?? k).join(', ')}</td>
                  <td className="text-right text-xs">{r.inspected ? `${r.found}/${r.inspected}` : '—'}</td>
                  <td className="pl-3">
                    <div className="flex flex-wrap gap-1 min-w-[180px]">
                      {r.icar_inputs.length === 0 ? <span className="text-xs text-soil-dark/40">—</span> : r.icar_inputs.map((x) => (
                        <span key={x.id} title={`${x.source_name} — ${x.institute.name}, ${x.institute.city}, ${x.institute.phone ?? ''}`}
                          className={`text-[11px] rounded-full px-2 py-0.5 ${x.lead_time_days ? 'bg-ochre/15 text-[#8a5a17]' : 'bg-leaf/10 text-leaf-deep'}`}>
                          {x.short}{x.lead_time_days ? ` · order ${x.lead_time_days} d ahead` : ''}
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

export function PesticidePanel({ p }: { p: PesticideBaseline }) {
  const max = Math.max(...p.chemical.map((c) => c[1]), 1)
  const latest = p.chemical[p.chemical.length - 1]
  return (
    <Card className="p-4">
      <h2 className="font-semibold flex items-center gap-2"><FlaskConical className="w-4 h-4 text-ember" /> Pesticide use baseline — {p.state}</h2>
      <p className="text-xs text-soil-dark/60 mt-0.5">
        The number "more targeted pesticide use" has to move. {p.state} used <b>{latest ? Math.round(latest[1]).toLocaleString('en-IN') : '—'} t</b> of chemical pesticides (technical grade) in {latest?.[0]} — <b>{p.latest_share_pct}%</b> of India, <b>#{p.rank}</b> of {p.states_ranked} states.
      </p>
      <div className="mt-4 flex items-end gap-1.5 h-32">
        {p.chemical.map(([year, v]) => (
          <div key={year} className="flex-1 flex flex-col items-center gap-1" title={`${year}: ${Math.round(v).toLocaleString('en-IN')} t`}>
            <span className="text-[9px] text-soil-dark/60">{(v / 1000).toFixed(1)}k</span>
            <span className="w-full rounded-t bg-ember/70" style={{ height: `${(v / max) * 96}px` }} />
            <span className="text-[9px] text-soil-dark/50">{year.slice(2)}</span>
          </div>
        ))}
      </div>
      <p className="mt-3 text-[11px] text-soil-dark/60">
        AnnRakshak's lever: chemical rungs come last and collapsed, advice only above the confidence gate, and the spray check vetoes wrong-class, wrong-crop and herbicide sprays before they happen.
      </p>
      <p className="mt-2 text-[10px] text-soil-dark/40">{p.source}. {p.unit_note}</p>
    </Card>
  )
}
