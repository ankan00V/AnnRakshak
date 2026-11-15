import { useEffect, useMemo, useState } from 'react'
import { Bell, BrainCircuit, Bug, CheckCircle2, FlaskRound, HelpCircle, History, Loader2, MapPin, Send, Timer, Users, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { CaseBundle, CaseListItem, CaseSatellite, CaseBrief } from '../api/types'
import { useAsync } from '../lib/hooks'
import { useAuth } from '../auth/AuthContext'
import { Bone, BoneLines, Card, ErrorBox, GradCamOverlay, Loading, Pill } from '../ui/kit'

const REASON_LABEL: Record<string, string> = {
  BELOW_FLOOR: 'Model unsure',
  BELOW_GATE: 'Likely, not confident',
  AMBIGUOUS_NO_CUE: 'Torn, no field check',
  ANSWER_DID_NOT_DISCRIMINATE: "Farmer couldn't tell",
  NOT_PHOTO_DIAGNOSABLE: 'Not photo-diagnosable',
  CROP_MISMATCH: 'Crop mismatch',
  CROP_NOT_SUPPORTED: 'No photo model for crop',
  NO_KB_ENTRY: 'No verified advice',
  FARMER_REQUEST: 'Farmer asked',
  FOLLOWUP_WORSE: 'Got worse after treatment',
  INSPECTION_FOUND: 'Found during alert check',
  LIVE_FEW_VIEWS: 'Live call: too few clear views',
  FEW_VIEWS: 'Live call: too few clear views',
  MINORITY_VIEWS: 'Live call: seen in only some views',
  LOOKALIKE: 'Live call: a look-alike problem',
  LAB_CLASS_CONFIRM: 'Needs a lab-class check',
  LAB_CLASS_BELOW_GATE: 'Lab-class, not confident',
  NOT_A_CROP_PHOTO: 'Not a crop photo',
  UNFAMILIAR_PHOTO: 'Unfamiliar photo',
  BELOW_GATE_LIVE: 'Live call: not confident',
}

/** A reason this table has no words for yet still reads as words, never as a
 *  code like LIVE_FEW_VIEWS on an officer's screen. */
export const reasonText = (r: string) =>
  REASON_LABEL[r] ?? (r.charAt(0) + r.slice(1).toLowerCase()).replace(/_/g, ' ')
/* The standalone "Expert validation" screen stood here.
 *
 * It listed the same cases as the district office's queue, opened the same
 * case view below it, and offered strictly less: no district or crop filter,
 * no bulk assign, no snooze, no keyboard triage, no saved views, no SLA
 * column. Two screens for one job, and the weaker one was where an expert
 * landed at sign-in. /expert now redirects to the queue; everything it was
 * built on is still here, and the queue has always imported it from this file.
 */

/** Evidence the photo cannot give: is the whole field losing vigour, or only
 *  the leaf in the picture? Clear Sentinel-2 / Landsat 8 scenes, newest last. */
function SatelliteEvidence({ s }: { s: CaseSatellite }) {
  const pts = s.series.length > 1 ? s.series : []
  const means = pts.map((p) => p.mean)
  const lo = Math.min(...means, s.latest.mean)
  const hi = Math.max(...means, s.latest.mean)
  const span = hi - lo || 0.1
  const W = 260
  const H = 48
  const x = (i: number) => (pts.length < 2 ? W : (i / (pts.length - 1)) * W)
  const y = (v: number) => H - ((v - lo) / span) * (H - 6) - 3
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.mean).toFixed(1)}`).join(' ')
  const falling = s.drop || (s.change ?? 0) < 0

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-[17px] font-semibold">Field greenness from satellite</h2>
        <span className="text-[12px] text-soil-dark/70">
          {s.latest.source} · {s.age_days === 0 ? 'today' : `${s.age_days}d ago`}
        </span>
      </div>

      <p className="mt-2 text-[15px]">
        <span className="text-[20px] font-semibold tabular-nums">{s.latest.mean.toFixed(2)}</span>
        {s.previous && (
          <span className="text-soil-dark/70">
            {' '}from {s.previous.mean.toFixed(2)} on {s.previous.on}
            {s.change != null && (
              <span className={falling ? 'text-ember font-medium' : 'text-leaf-deep font-medium'}>
                {' '}({s.change > 0 ? '+' : ''}{s.change.toFixed(2)})
              </span>
            )}
          </span>
        )}
      </p>

      {pts.length > 1 && (
        <svg viewBox={`0 0 ${W} ${H}`} className="mt-3 w-full h-12" role="img"
          aria-label={`Greenness over the last ${pts.length} clear scenes, ending at ${s.latest.mean.toFixed(2)}`}>
          <path d={line} fill="none" stroke={falling ? '#b0472a' : '#3d6b4a'} strokeWidth="1.5"
            strokeLinecap="round" strokeLinejoin="round" />
          <circle cx={x(pts.length - 1)} cy={y(pts[pts.length - 1].mean)} r="2.5"
            fill={falling ? '#b0472a' : '#3d6b4a'} />
        </svg>
      )}

      <p className="mt-2 text-[13px] text-soil-dark/70">
        {s.drop
          ? 'The field lost greenness between two clear scenes — the whole field is under stress, not just this leaf.'
          : s.quiet_stage
            ? 'The crop is at a stage where greenness falls anyway, so this is not read as stress.'
            : 'No unusual fall in greenness: whatever this is, it has not spread across the field yet.'}
      </p>
    </Card>
  )
}


/** "Bhandara, Gondia +3" — a roving officer covers too many to list. */
function districtLabel(districts: string[]): string {
  if (districts.length === 0) return 'no district'
  const shown = districts.slice(0, 2).join(', ')
  return districts.length > 2 ? `${shown} +${districts.length - 2}` : shown
}

/** Hand a case on: wrong speciality, a queue too long, or off for the day. */
function HandOff({ b, onHandedOff }: { b: CaseBundle; onHandedOff: (to: CaseBrief) => void }) {
  // Who else is on the books is the office's business, not every officer's: an
  // ordinary desk may give a case up, and the system decides where it goes.
  const { me } = useAuth()
  const mayPlaceByName = me?.profile?.supervisor === true
  const officers = useAsync(
    () => (mayPlaceByName ? api.officers(b.farm.district) : Promise.resolve([])),
    [b.farm.district, mayPlaceByName])
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const hand = async (to: number | null) => {
    setBusy(true)
    setError(null)
    try {
      const landed = await api.reassignCase(b.case.id, to)
      setOpen(false)
      // Deliberately no reload of this case. It has left this desk, and the
      // server rightly refuses a case that is no longer this officer's to
      // read — so asking for it again answered "case not found" to the
      // officer who had just done the right thing. The reassign itself says
      // where the case went; whoever owns the screen decides what to show.
      onHandedOff(landed)
    } catch (e) {
      setError(e as Error)
    } finally {
      setBusy(false)
    }
  }

  const others = (officers.data ?? []).filter((o) => o.user_id !== b.case.assigned_to)
  return (
    <div className="relative">
      <button onClick={() => setOpen((v) => !v)} disabled={busy}
        aria-expanded={open}
        className="flex min-h-[36px] items-center gap-1.5 rounded-full bg-white px-3.5 text-[13px] font-semibold text-soil-dark/85 ring-1 ring-soil-dark/15 hover:bg-[#f8f6f0] disabled:opacity-50">
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Users className="h-4 w-4" />}
        {b.case.assigned_name ? `With ${b.case.assigned_name}` : 'Unassigned'} · hand on
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-2 w-72 rounded-2xl bg-white p-2 shadow-[0_18px_40px_-16px_rgba(43,29,18,0.45)] ring-1 ring-soil-dark/10">
          <button onClick={() => hand(null)}
            className="w-full rounded-xl px-3 py-2.5 text-left text-[14px] hover:bg-[#f8f6f0]">
            <span className="font-medium">Whoever is freest</span>
            <span className="block text-[12px] text-soil-dark/70">Routes by open cases, then who has waited longest</span>
          </button>
          {mayPlaceByName && <div className="my-1 border-t border-soil-dark/10" />}
          {mayPlaceByName && others.length === 0 && (
            <p className="px-3 py-2 text-[13px] text-soil-dark/70">No other officer is verified yet.</p>
          )}
          {others.map((o) => (
            <button key={o.user_id} onClick={() => hand(o.user_id)}
              className="flex w-full items-center justify-between gap-2 rounded-xl px-3 py-2.5 text-left text-[14px] hover:bg-[#f8f6f0]">
              <span>
                {o.name}
                <span className="block text-[12px] text-soil-dark/70">{districtLabel(o.districts)}</span>
              </span>
              <span className="text-[12px] tabular-nums text-soil-dark/70 shrink-0">{o.open_cases} open</span>
            </button>
          ))}
        </div>
      )}
      {error && <p className="mt-1 text-[12px] text-ember">{error.message}</p>}
    </div>
  )
}

/** How long this farmer has been waiting. Past a day it is the first thing an
 *  officer should see about a case. */
function Waiting({ c, active }: { c: CaseListItem; active: boolean }) {
  if (!c.created_at || c.status !== 'open') return null
  const hours = (Date.now() - new Date(c.created_at).getTime()) / 3.6e6
  if (hours < 6) return null
  const label = hours < 48 ? `${Math.round(hours)} h` : `${Math.round(hours / 24)} days`
  return <Pill tone={active ? 'dark' : hours > 24 ? 'ember' : 'neutral'}>waiting {label}</Pill>
}

/** The clock on this desk. The case moves to the next eligible officer when it
 *  runs out, so the officer holding it should be able to see it rather than
 *  find out by losing the case. */
export function RespondBy({ c, active }: { c: CaseBrief; active?: boolean }) {
  if (c.status !== 'open' || !c.respond_by) return null
  const left = (new Date(c.respond_by).getTime() - Date.now()) / 3.6e6
  if (left > 4) return null          // plenty of time: not worth the ink
  const late = left <= 0
  return (
    <Pill tone={active ? 'dark' : late ? 'ember' : 'ochre'}>
      {late ? 'moving on' : left < 1 ? `${Math.max(1, Math.round(left * 60))} min left` : `${Math.round(left)} h left`}
    </Pill>
  )
}

export function CaseRow({ c, active, onClick }: { c: CaseListItem; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className={`w-full text-left flex gap-3 rounded-2xl p-3 border transition-colors ${active ? 'bg-leaf-deep text-cream border-leaf-deep' : 'bg-white border-soil-dark/10 hover:border-leaf/40'}`}>
      <span className="shrink-0 w-14 h-14 rounded-xl overflow-hidden bg-soil-dark/10">
        {c.photo && <img src={c.photo} alt="" className="w-full h-full object-cover" />}
      </span>
      <span className="flex-1 min-w-0">
        <span className="flex items-center justify-between gap-2">
          <span className="text-sm font-semibold truncate">#{c.id} · {c.farmer_name}</span>
          {c.status === 'open' && <span className={`text-[12px] ${active ? 'text-cream/70' : 'text-soil-dark/70'}`}>#{c.queue_position}</span>}
        </span>
        <span className={`block text-[13px] truncate ${active ? 'text-cream/70' : 'text-soil-dark/70'}`}>{c.crop} · {c.district}</span>
        <span className="mt-1 flex flex-wrap gap-1">
          <Pill tone={active ? 'dark' : 'sky'}>{reasonText(c.reason)}</Pill>
          {c.model_top && <Pill tone={active ? 'dark' : 'neutral'}>{c.model_top.name} {Math.round((c.model_top.confidence ?? 0) * 100)}%</Pill>}
          {c.severity === 'high' && <Pill tone="ember">high</Pill>}
          {c.assigned_name
            ? <Pill tone={active ? 'dark' : 'leaf'}>{c.assigned_name}</Pill>
            : <Pill tone={active ? 'dark' : 'ochre'}>unassigned</Pill>}
          <Waiting c={c} active={active} />
          <RespondBy c={c} active={active} />
        </span>
      </span>
    </button>
  )
}

function useElapsed() {
  const [start] = useState(() => Date.now())
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  const s = Math.floor((now - start) / 1000)
  return { s, label: `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}` }
}

export function CaseView({ id, onBack, onResolved, onHandedOff }: {
  id: number; onBack: () => void; onResolved: () => void; onHandedOff: (to: CaseBrief) => void
}) {
  const bundle = useAsync(() => api.caseBundle(id), [id])
  if (bundle.loading && !bundle.data) return <CaseSkeleton />
  if (bundle.error) return <ErrorBox error={bundle.error} onRetry={bundle.reload} />
  return <CaseDetail key={id} b={bundle.data!} onBack={onBack} onHandedOff={onHandedOff}
    onResolved={() => { bundle.reload(); onResolved() }} />
}


/** The queue and the case, while they load. */
function CaseRowBone() {
  return (
    <Card className="p-3 flex items-center gap-3">
      <Bone className="w-10 h-10 rounded-xl shrink-0" />
      <div className="flex-1 space-y-2">
        <Bone className="h-3.5 w-3/5" />
        <Bone className="h-2.5 w-2/5 rounded-full" />
      </div>
    </Card>
  )
}

export function QueueSkeleton() {
  return (
    <Loading label="Loading the queue">
      <ul className="space-y-2">
        {Array.from({ length: 5 }, (_, i) => <li key={i}><CaseRowBone /></li>)}
      </ul>
    </Loading>
  )
}

function CaseSkeleton() {
  return (
    <Loading label="Loading the case">
      <div className="space-y-4">
        <Bone className="h-8 w-40" />
        <div className="grid md:grid-cols-2 gap-4">
          <Bone className="h-64 w-full rounded-2xl" />
          <Card className="p-4 space-y-3">
            <Bone className="h-4 w-36" />
            <BoneLines lines={4} />
          </Card>
        </div>
        {Array.from({ length: 2 }, (_, i) => (
          <Card key={i} className="p-4 space-y-3">
            <Bone className="h-4 w-44" />
            <BoneLines lines={3} />
          </Card>
        ))}
      </div>
    </Loading>
  )
}

function CaseDetail({ b, onBack, onResolved, onHandedOff }: {
  b: CaseBundle; onBack: () => void; onResolved: () => void; onHandedOff: (to: CaseBrief) => void
}) {
  const timer = useElapsed()
  const [photo, setPhoto] = useState(0)
  const [showCam, setShowCam] = useState(true)
  const open = b.case.status === 'open'
  const top = b.model.hypotheses[0]

  const pctOf = (c: number | null | undefined) => Math.round((c ?? 0) * 100)

  return (
    <div className="space-y-5">
      {/* Who, where, why, and the clock — the line an officer reads before the photo. */}
      <Card className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="font-instrument-serif text-[34px] leading-none text-[#1d3a24]">Case #{b.case.id}</h1>
              <span className={`rounded-full px-3 py-1 text-[13px] font-semibold ${open ? 'bg-[#fdf5e6] text-[#9a6210]' : 'bg-[#eef6ea] text-[#2f6a39]'}`}>
                {open ? 'Open' : 'Resolved'}
              </span>
            </div>
            <p className="mt-2 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[14px] text-soil-dark/75">
              <MapPin className="h-4 w-4 shrink-0" aria-hidden />
              <Link to={`/officer/farm/${b.farm.id}`} className="font-semibold text-soil-dark hover:text-leaf-deep hover:underline underline-offset-2">
                {b.farm.farmer_name}
              </Link>
              <span>· {b.farm.crop_name} · {b.farm.district} · {b.farm.stage_name}, {b.farm.das} days · {b.farm.area_acres} acres</span>
            </p>
            <p className="mt-2.5 inline-flex rounded-full bg-sky-50 px-3 py-1 text-[13px] font-medium text-sky-800">
              Here because: {reasonText(b.case.reason)}
            </p>
          </div>
          <button onClick={onBack} aria-label="Close the case"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#f8f6f0] text-soil-dark/70 hover:bg-[#f1ede2] hover:text-soil-dark">
            <X className="h-5 w-5" />
          </button>
        </div>
        {open && (
          <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-soil-dark/[0.07] pt-4">
            <span className={`flex min-h-[36px] items-center gap-1.5 rounded-full px-3.5 text-[14px] font-semibold tabular-nums ${
              timer.s > 180 ? 'bg-[#fdf0ed] text-[#b5381c]' : 'bg-[#eef6ea] text-[#2f6a39]'}`}>
              <Timer className="h-4 w-4" aria-hidden /> {timer.label} <span className="font-normal opacity-75">/ 3:00 target</span>
            </span>
            {b.case.respond_by && (
              <span className="text-[13px] text-soil-dark/75">
                {new Date(b.case.respond_by).getTime() > Date.now()
                  ? `Answer by ${new Date(b.case.respond_by).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
                  : 'Past its time — moving to another desk'}
                {b.case.handovers > 0 && ` · ${b.case.handovers} desk${b.case.handovers === 1 ? '' : 's'} before you`}
              </span>
            )}
            <span className="ml-auto"><HandOff b={b} onHandedOff={onHandedOff} /></span>
          </div>
        )}
      </Card>

      <div className="grid gap-5 xl:grid-cols-[1.15fr_1fr]">
        <Card className="p-2">
          {b.photos.length > 0 ? (
            <>
              <div className="relative aspect-[4/3] w-full overflow-hidden rounded-[18px] bg-[#eef3e6]">
                <img src={b.photos[photo]} alt="" className="h-full w-full object-cover" />
                {showCam && b.heatmaps?.[photo] && <GradCamOverlay heatmap={b.heatmaps[photo]!} />}
                {b.heatmaps?.[photo] && (
                  <button onClick={() => setShowCam((v) => !v)} aria-pressed={showCam}
                    className="absolute bottom-3 left-3 rounded-full bg-black/60 px-3 py-1.5 text-[13px] text-white backdrop-blur-sm">
                    {showCam ? 'Hide' : 'Show'} where the AI looked
                  </button>
                )}
                {b.photos.length > 1 && (
                  <span className="absolute right-3 top-3 rounded-full bg-black/60 px-2.5 py-1 text-[12px] font-medium text-white tabular-nums">
                    {photo + 1} / {b.photos.length}
                  </span>
                )}
              </div>
              {b.photos.length > 1 && (
                <div className="flex gap-2 px-1 pb-1 pt-2">
                  {b.photos.map((p, i) => (
                    <button key={p} onClick={() => setPhoto(i)} aria-label={`Photo ${i + 1}`}
                      className={`h-16 w-16 overflow-hidden rounded-xl ring-2 transition ${i === photo ? 'ring-[#d29a3a]' : 'ring-transparent opacity-80 hover:opacity-100'}`}>
                      <img src={p} alt="" className="h-full w-full object-cover" />
                    </button>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="flex aspect-[4/3] flex-col items-center justify-center gap-1 rounded-[18px] bg-[#f8f6f0] px-6 text-center">
              <p className="text-[15px] font-semibold text-soil-dark/80">No photograph</p>
              <p className="text-[13px] leading-relaxed text-soil-dark/70">
                The farmer reported this without one. Their words are beside this panel.
              </p>
            </div>
          )}
        </Card>

        <div className="space-y-5">
          <Card className="p-5">
            <h2 className="flex items-center gap-2 text-[17px] font-semibold">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#eef3e6] text-[#2f6a39]"><BrainCircuit className="h-5 w-5" aria-hidden /></span>
              What the model thinks
              {b.model.is_stub && <span className="rounded-full bg-[#fdf5e6] px-2.5 py-0.5 text-[12px] font-semibold text-[#9a6210]">demo model</span>}
            </h2>
            {b.model.hypotheses.length === 0 ? (
              <p className="mt-3 text-[14px] text-soil-dark/75">No model output for this case.</p>
            ) : (
              <ul className="mt-4 space-y-3">
                {b.model.hypotheses.map((h, i) => (
                  <li key={h.id}>
                    <div className="flex items-baseline justify-between gap-3 text-[14px]">
                      <span className={i === 0 ? 'font-semibold' : 'text-soil-dark/85'}>{h.name}</span>
                      <span className={`tabular-nums ${i === 0 ? 'font-semibold' : 'text-soil-dark/70'}`}>{pctOf(h.confidence)}%</span>
                    </div>
                    <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-soil-dark/[0.07]">
                      <div className={`h-full rounded-full ${i === 0 ? 'bg-[#2f6a39]' : 'bg-[#2f6a39]/30'}`} style={{ width: `${pctOf(h.confidence)}%` }} />
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {b.model.version && (
              <details className="mt-3 text-[12px] text-soil-dark/65">
                <summary className="cursor-pointer select-none hover:text-soil-dark/85">Model version</summary>
                <p className="mt-1 break-all">{b.model.version}</p>
              </details>
            )}
          </Card>

          {b.farmer_report.length > 0 && (
            <Card className="bg-[#fdf0ed] p-5">
              <h2 className="flex items-center gap-2 text-[16px] font-semibold text-[#9a2f17]">
                <HelpCircle className="h-5 w-5" aria-hidden /> What the farmer reported
              </h2>
              {b.farmer_report.map((r, i) => (
                <p key={i} className="mt-2 rounded-xl bg-white/70 p-3 text-[15px] leading-relaxed">“{r.answer}”</p>
              ))}
            </Card>
          )}

          {b.doubt_doctor.length > 0 && (
            <Card className="bg-[#fdf5e6] p-5">
              <h2 className="flex items-center gap-2 text-[16px] font-semibold text-[#7a4f12]">
                <HelpCircle className="h-5 w-5" aria-hidden /> The farmer's answer in the field
              </h2>
              {b.doubt_doctor.map((d, i) => (
                <div key={i} className="mt-2 rounded-xl bg-white/70 p-3 text-[14px]">
                  <p className="text-soil-dark/75">“{d.question}”</p>
                  <p className="mt-1 text-[15px] font-semibold">→ {d.answer === 'unknown' ? "Can't tell" : d.answer === 'yes' ? 'Yes' : d.answer === 'no' ? 'No' : d.answer}</p>
                </div>
              ))}
            </Card>
          )}
        </div>
      </div>

      {/* The rest of the field's story: what the traps say, what the app has
          already warned about, and what this farm has had before. */}
      <Card className="p-5">
        <h2 className="text-[17px] font-semibold">This farm</h2>
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <div className="rounded-2xl bg-[#f8f6f0] p-4">
            <h3 className="flex items-center gap-1.5 text-[14px] font-semibold"><Bug className="h-4 w-4 text-[#2f6a39]" aria-hidden /> Trap counts</h3>
            {b.trap_readings.length === 0 ? <p className="mt-2 text-[14px] text-soil-dark/70">None recorded</p> : (
              <ul className="mt-2 space-y-1.5 text-[14px]">
                {b.trap_readings.slice(0, 5).map((t, i) => (
                  <li key={i} className="flex justify-between gap-2 tabular-nums">
                    <span className="text-soil-dark/75">{t.recorded_on}</span>
                    <span className={t.per_trap_night >= 8 ? 'font-semibold text-[#b5381c]' : ''}>{t.per_trap_night} / trap / night</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="rounded-2xl bg-[#f8f6f0] p-4">
            <h3 className="flex items-center gap-1.5 text-[14px] font-semibold"><Bell className="h-4 w-4 text-[#2f6a39]" aria-hidden /> Recent alerts</h3>
            {b.recent_alerts.length === 0 ? <p className="mt-2 text-[14px] text-soil-dark/70">None</p> : (
              <ul className="mt-2 space-y-1.5 text-[14px]">
                {b.recent_alerts.slice(0, 5).map((a) => (
                  <li key={a.id}>
                    <span className="block truncate font-medium">{a.name}</span>
                    <span className="block text-[12px] text-soil-dark/70">{TRIGGER_WORD[a.trigger] ?? a.trigger} · {OUTCOME_WORD[a.outcome ?? 'open'] ?? a.outcome}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="rounded-2xl bg-[#f8f6f0] p-4">
            <h3 className="flex items-center gap-1.5 text-[14px] font-semibold"><History className="h-4 w-4 text-[#2f6a39]" aria-hidden /> History &amp; follow-ups</h3>
            <ul className="mt-2 space-y-1.5 text-[14px]">
              {b.farm_history.map((h, i) => (
                <li key={i}><span className="capitalize">{h.final_label.replace(/_/g, ' ')}</span> <span className="text-soil-dark/70">· {h.verdict}</span></li>
              ))}
              {b.followups.map((f, i) => (
                <li key={`f${i}`} className="text-soil-dark/80">Follow-up {f.due_on}: {f.response ? f.response.replace(/_/g, ' ') : 'pending'}</li>
              ))}
              {b.farm_history.length === 0 && b.followups.length === 0 && <li className="text-soil-dark/70">First problem on record</li>}
            </ul>
          </div>
        </div>
      </Card>

      {b.satellite && <SatelliteEvidence s={b.satellite} />}

      {open ? <Decision b={b} top={top?.id} elapsed={timer.s} onResolved={onResolved} /> : (
        <Card className="flex items-center gap-2 bg-[#eef6ea] p-5 text-[15px] font-semibold text-[#2f6a39]">
          <CheckCircle2 className="h-5 w-5" /> Resolved
        </Card>
      )}

      {b.icar_referral?.length > 0 && <IcarReferral b={b} />}
    </div>
  )
}

const TRIGGER_WORD: Record<string, string> = {
  weather: 'Weather', phenology: 'Crop stage', 'weather+phenology': 'Weather + crop stage', trap: 'Trap count', spread: 'Confirmed nearby',
}
const OUTCOME_WORD: Record<string, string> = {
  open: 'not checked yet', snoozed: 'reminded', found: 'farmer found it', nothing_found: 'checked, nothing found',
}

const DFIELD = 'mt-1.5 w-full min-h-[46px] rounded-2xl bg-[#f8f6f0] px-3.5 text-[14px] font-normal text-soil-dark ring-1 ring-soil-dark/10 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#4b8b3b]'

function Decision({ b, top, elapsed, onResolved }: { b: CaseBundle; top?: string; elapsed: number; onResolved: () => void }) {
  // The verdict is recorded under the signed-in expert (the server takes the name from the session).
  const name = useAuth().me?.name ?? ''
  // No default beyond the model's own guess: pre-filling some other label would nudge the reviewer.
  const [label, setLabel] = useState(top && b.candidate_labels.some((c) => c.id === top) ? top : '')
  const [notes, setNotes] = useState('')
  const [lab, setLab] = useState(false)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState<{ verdict: string; spread: number; secs: number; label: string } | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const groups = useMemo(() => {
    const photo = b.candidate_labels.filter((c) => c.tier === 'diagnosable')
    const insp = b.candidate_labels.filter((c) => c.tier !== 'diagnosable')
    return [['Photo-diagnosable', photo], ['Needs inspection', insp]] as const
  }, [b.candidate_labels])

  const submit = async () => {
    if (!label) return
    setBusy(true)
    setError(null)
    try {
      const r = await api.resolveCase(b.case.id, {
        verdict: label === top ? 'confirmed' : 'corrected', final_label: label, expert_name: name, notes: notes || null, referred_to_lab: lab,
      })
      setDone({ verdict: r.verdict, spread: r.spread_alerts, secs: elapsed, label })
      onResolved()
    } catch (e) {
      setError(e as Error)
    } finally {
      setBusy(false)
    }
  }

  if (done) {
    return (
      <Card className="bg-[#eef6ea] p-5 lg:p-6">
        <p className="flex items-center gap-2 text-[17px] font-semibold text-[#2f6a39]"><CheckCircle2 className="w-5 h-5" /> {done.verdict === 'confirmed' ? 'Confirmed' : 'Corrected'} in {Math.floor(done.secs / 60)}:{String(done.secs % 60).padStart(2, '0')}</p>
        <ul className="mt-3 space-y-1.5 text-[14px] text-soil-dark/85">
          {done.label === 'healthy' ? (
            <>
              <li>• The farmer is told their crop is fine — no treatment, nothing to buy.</li>
              <li>• No neighbour was warned, and the model's guess is on record as wrong.</li>
            </>
          ) : done.label === 'other' ? (
            <>
              <li>• The farmer sees your note and the referral, and no advisory the app cannot stand behind.</li>
              <li>• Logged as a problem the model cannot yet name.</li>
            </>
          ) : (
            <>
              <li>• The farmer now sees the expert-confirmed advisory in their language.</li>
              <li>• {done.spread} nearby {b.farm.crop} farm{done.spread === 1 ? '' : 's'} within 5 km received an inspection alert.</li>
              <li>• District confirmation counts updated — this is how the system learns from field confirmations.</li>
            </>
          )}
        </ul>
      </Card>
    )
  }

  return (
    <Card className="space-y-4 p-5 ring-2 ring-[#4b8b3b]/30 lg:p-6">
      <div>
        <h2 className="text-[20px] font-semibold tracking-tight">Your decision</h2>
        <p className="mt-1 text-[14px] text-soil-dark/70">What you choose is what the farmer is told, under your name.</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <label className="block text-[13px] font-semibold text-soil-dark/80">
          Final diagnosis
          <select value={label} onChange={(e) => setLabel(e.target.value)} className={DFIELD}>
            {!label && <option value="" disabled>Choose the final diagnosis…</option>}
            {groups.map(([g, items]) => items.length > 0 && (
              <optgroup key={g} label={g}>
                {items.map((c) => <option key={c.id} value={c.id}>{c.name}{c.id === top ? ' — model top guess' : ''}</option>)}
              </optgroup>
            ))}
            {/* The model only knows what it was trained on. A crop can be fine,
                and a real problem can sit outside the knowledge base entirely. */}
            <optgroup label="Neither">
              <option value="healthy">Healthy — nothing wrong with this crop</option>
              <option value="other">Something else — not in this list</option>
            </optgroup>
          </select>
        </label>
        <label className="block text-[13px] font-semibold text-soil-dark/80">
          Reviewing expert
          <input value={name} readOnly aria-readonly className={`${DFIELD} bg-soil-dark/[0.05] text-soil-dark/80`} />
        </label>
      </div>
      <label className="block text-[13px] font-semibold text-soil-dark/80">
        {label === 'other' ? 'What is it? (required — the farmer is shown this)' : 'Note to farmer (optional)'}
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2}
          placeholder={label === 'other' ? 'Name the problem, e.g. "Zinc deficiency — interveinal chlorosis on older leaves"' : undefined}
          className={`mt-1.5 w-full rounded-2xl bg-[#f8f6f0] px-3.5 py-2.5 text-[14px] font-normal ring-1 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#4b8b3b] ${
            label === 'other' && !notes.trim() ? 'ring-[#b5381c]/50' : 'ring-soil-dark/10'}`} />
      </label>
      {label === 'healthy' && (
        <p className="rounded-2xl bg-[#eef6ea] p-3.5 text-[14px] text-[#2f5a24]">
          Recorded as healthy: no advisory, no spread alert, and the model's guess is marked wrong.
        </p>
      )}
      {label === 'other' && (
        <p className="rounded-2xl bg-[#fdf5e6] p-3.5 text-[14px] text-[#7a4f12]">
          Outside the knowledge base, so the app offers no treatment of its own — the farmer sees your
          note and the referral. It is logged as a gap for the team.
        </p>
      )}
      <label className="flex min-h-[44px] cursor-pointer items-center gap-2.5 rounded-2xl bg-[#f8f6f0] px-3.5 text-[14px]">
        <input type="checkbox" checked={lab} onChange={(e) => setLab(e.target.checked)} className="h-4 w-4 accent-[#2f6a39]" />
        <FlaskRound className="w-4 h-4 text-soil-dark/70" /> Refer sample to a diagnostic lab / KVK
      </label>
      {error && <ErrorBox error={error} />}
      <button onClick={submit} disabled={busy || !label || !name.trim() || (label === 'other' && !notes.trim())}
        className="flex min-h-[52px] w-full items-center justify-center gap-2 rounded-full bg-[#1d4a2c] text-[16px] font-semibold text-white shadow-[0_12px_24px_-14px_rgba(29,74,44,0.8)] hover:bg-[#245a35] disabled:opacity-50 disabled:shadow-none">
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
        {label === 'healthy' ? 'Record as healthy'
          : label === 'other' ? 'Record and refer'
            : label === top ? 'Confirm model diagnosis' : 'Correct and send'}
      </button>
    </Card>
  )
}

const ICAR_TYPE: Record<string, string> = {
  biocontrol: 'Bio-control', variety: 'Resistant variety', practice: 'Practice',
  monitoring: 'Monitoring', app: 'App / decision tool', reference: 'Reference',
}

/** Referral options straight from the ICAR technology repository: what to
 *  recommend beyond our ladder, and which institute to route the farmer or the
 *  extension office to. */
function IcarReferral({ b }: { b: CaseBundle }) {
  const names = Object.fromEntries(b.candidate_labels.map((c) => [c.id, c.name]))
  return (
    <Card className="p-5 lg:p-6">
      <h2 className="text-[17px] font-semibold">ICAR technologies &amp; referral</h2>
      <p className="mt-1 text-[13px] text-soil-dark/70">From the ICAR technology repository, matched to the suspected problems, then crop-level tools.</p>
      <ul className="mt-4 grid gap-3 md:grid-cols-2">
        {b.icar_referral.map((x) => (
          <li key={x.id} className="rounded-2xl bg-[#f8f6f0] p-4 text-[14px]">
            <div className="flex flex-wrap gap-1">
              <Pill tone="leaf">{ICAR_TYPE[x.type]}</Pill>
              <Pill>{x.for_target ? `for ${names[x.for_target] ?? x.for_target}` : `${b.farm.crop_name} (crop-level)`}</Pill>
            </div>
            <p className="mt-2 font-semibold leading-snug">{x.source_name}</p>
            <p className="mt-1 text-[13px] text-soil-dark/70 leading-snug">{x.summary}</p>
            {x.claim && <p className="mt-1 text-[13px] text-leaf-deep">{x.claim}</p>}
            {x.lead_time_days && <p className="mt-1 text-[13px] text-[#8a5a17]">Needs {x.lead_time_days} days' notice to the institute.</p>}
            <p className="mt-1.5 text-[13px] text-soil-dark/70">
              {x.institute.name}, {x.institute.city} · <a className="text-leaf-deep" href={`tel:${(x.institute.phone ?? '').replace(/[^0-9+]/g, '')}`}>{x.institute.phone}</a>
              {x.institute.email && <> · <span title={x.institute.email_note}>{x.institute.email}{x.institute.email_note ? ' (unverified)' : ''}</span></>}
            </p>
          </li>
        ))}
      </ul>
    </Card>
  )
}
