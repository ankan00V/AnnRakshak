import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, Bug, CheckCircle2, ClipboardList, FlaskRound, HelpCircle, Inbox, Loader2, MapPin, Send, Timer, UserCheck, Users } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { CaseBundle, CaseListItem, CaseSatellite } from '../api/types'
import { useAsync } from '../lib/hooks'
import { useAuth } from '../auth/AuthContext'
import { Bone, BoneLines, Card, ErrorBox, GradCamOverlay, Loading, Pill } from '../ui/kit'
import AccountMenu from '../auth/AccountMenu'
import BrandMark from '../ui/BrandMark'

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
}

export default function ExpertConsole() {
  const [tab, setTab] = useState<'open' | 'resolved'>('open')
  // The district's queue is the default view; an officer narrows to their own.
  const [scope, setScope] = useState<'mine' | 'all'>('all')
  const list = useAsync(() => api.cases(tab, scope), [tab, scope])
  const [selected, setSelected] = useState<number | null>(null)

  return (
    <div className="min-h-screen bg-cream text-soil-dark">
      <header className="bg-soil-dark text-cream">
        <div className="max-w-7xl mx-auto px-4 md:px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight"><BrandMark size={30} />AnnRakshak</Link>
            <span className="text-cream/40">/</span>
            <span className="flex items-center gap-1.5 text-sm"><UserCheck className="w-4 h-4 text-ochre" /> Expert validation</span>
          </div>
          <nav className="flex items-center gap-4 text-sm text-cream/70">
            <Link to="/officer" className="hover:text-cream">Officials' dashboard</Link>
            <AccountMenu />
          </nav>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 md:px-6 py-5 grid md:grid-cols-[340px_1fr] gap-5">
        <aside className={`${selected ? 'hidden md:block' : ''}`}>
          <div className="flex rounded-full bg-white border border-soil-dark/10 p-1 mb-3">
            {(['open', 'resolved'] as const).map((s) => (
              <button key={s} onClick={() => { setTab(s); setSelected(null) }}
                className={`flex-1 rounded-full py-1.5 text-sm font-medium capitalize ${tab === s ? 'bg-leaf-deep text-cream' : 'text-soil-dark/60'}`}>
                {s}
              </button>
            ))}
          </div>
          <div className="flex items-center justify-between gap-2 mb-3 px-1">
            <div className="flex rounded-full bg-white border border-soil-dark/10 p-0.5 text-xs">
              {([['mine', 'My queue'], ['all', 'All district']] as const).map(([k, label]) => (
                <button key={k} onClick={() => { setScope(k); setSelected(null) }}
                  className={`rounded-full px-3 py-1 font-medium ${scope === k ? 'bg-leaf-deep text-cream' : 'text-soil-dark/60'}`}>
                  {label}
                </button>
              ))}
            </div>
            {list.data && <span className="text-xs text-soil-dark/60">{list.data.length} case{list.data.length === 1 ? '' : 's'}</span>}
          </div>
          {list.loading && !list.data && <QueueSkeleton />}
          {list.error && <ErrorBox error={list.error} onRetry={list.reload} />}
          {list.data && list.data.length === 0 && (
            <Card className="p-6 text-center text-sm text-soil-dark/60">
              <Inbox className="w-6 h-6 mx-auto mb-2 text-leaf" />
              Queue is clear.
            </Card>
          )}
          <ul className="space-y-2">
            {list.data?.map((c) => (
              <li key={c.id}>
                <CaseRow c={c} active={selected === c.id} onClick={() => setSelected(c.id)} />
              </li>
            ))}
          </ul>
        </aside>

        <main>
          {selected ? (
            <CaseView id={selected} onBack={() => setSelected(null)} onResolved={() => { list.reload(); }} />
          ) : (
            <Card className="hidden md:flex p-10 flex-col items-center justify-center text-center text-soil-dark/60 min-h-[420px]">
              <ClipboardList className="w-8 h-8 text-leaf" />
              <p className="mt-3 font-instrument-serif text-2xl text-soil-dark">Pick a case</p>
              <p className="mt-1 text-sm max-w-sm">
                Each case arrives pre-packed: photos, the model's ranked guesses, the farmer's field answers, trap counts and alerts — so a review takes under three minutes.
              </p>
            </Card>
          )}
        </main>
      </div>
    </div>
  )
}


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
    <Card className="p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-soil-dark/50">
          Field greenness (NDVI)
        </h3>
        <span className="text-[11px] text-soil-dark/50">
          {s.latest.source} · {s.age_days === 0 ? 'today' : `${s.age_days}d ago`}
        </span>
      </div>

      <p className="mt-2 text-sm">
        <span className="font-semibold tabular-nums">{s.latest.mean.toFixed(2)}</span>
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

      <p className="mt-2 text-xs text-soil-dark/70">
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
function HandOff({ b, onDone }: { b: CaseBundle; onDone: () => void }) {
  const officers = useAsync(() => api.officers(b.farm.district), [b.farm.district])
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const hand = async (to: number | null) => {
    setBusy(true)
    setError(null)
    try {
      await api.reassignCase(b.case.id, to)
      setOpen(false)
      onDone()
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
        className="flex items-center gap-1.5 text-xs font-medium text-soil-dark/70 hover:text-soil-dark rounded-full border border-soil-dark/15 px-3 py-1.5 disabled:opacity-50">
        {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Users className="w-3.5 h-3.5" />}
        {b.case.assigned_name ? `With ${b.case.assigned_name}` : 'Unassigned'} · hand on
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-1 w-72 rounded-2xl border border-soil-dark/15 bg-white shadow-xl p-2">
          <button onClick={() => hand(null)}
            className="w-full text-left rounded-xl px-3 py-2 text-sm hover:bg-cream">
            <span className="font-medium">Whoever is freest</span>
            <span className="block text-[11px] text-soil-dark/60">Routes by open cases, then who has waited longest</span>
          </button>
          <div className="my-1 border-t border-soil-dark/10" />
          {others.length === 0 && (
            <p className="px-3 py-2 text-xs text-soil-dark/60">No other officer is verified yet.</p>
          )}
          {others.map((o) => (
            <button key={o.user_id} onClick={() => hand(o.user_id)}
              className="w-full text-left rounded-xl px-3 py-2 text-sm hover:bg-cream flex items-center justify-between gap-2">
              <span>
                {o.name}
                <span className="block text-[11px] text-soil-dark/60">{districtLabel(o.districts)}</span>
              </span>
              <span className="text-[11px] tabular-nums text-soil-dark/60 shrink-0">{o.open_cases} open</span>
            </button>
          ))}
        </div>
      )}
      {error && <p className="mt-1 text-[11px] text-ember">{error.message}</p>}
    </div>
  )
}

function CaseRow({ c, active, onClick }: { c: CaseListItem; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className={`w-full text-left flex gap-3 rounded-2xl p-3 border transition-colors ${active ? 'bg-leaf-deep text-cream border-leaf-deep' : 'bg-white border-soil-dark/10 hover:border-leaf/40'}`}>
      <span className="shrink-0 w-14 h-14 rounded-xl overflow-hidden bg-soil-dark/10">
        {c.photo && <img src={c.photo} alt="" className="w-full h-full object-cover" />}
      </span>
      <span className="flex-1 min-w-0">
        <span className="flex items-center justify-between gap-2">
          <span className="text-sm font-semibold truncate">#{c.id} · {c.farmer_name}</span>
          {c.status === 'open' && <span className={`text-[11px] ${active ? 'text-cream/70' : 'text-soil-dark/50'}`}>#{c.queue_position}</span>}
        </span>
        <span className={`block text-xs truncate ${active ? 'text-cream/70' : 'text-soil-dark/60'}`}>{c.crop} · {c.district}</span>
        <span className="mt-1 flex flex-wrap gap-1">
          <Pill tone={active ? 'dark' : 'sky'}>{REASON_LABEL[c.reason] ?? c.reason}</Pill>
          {c.model_top && <Pill tone={active ? 'dark' : 'neutral'}>{c.model_top.name} {Math.round((c.model_top.confidence ?? 0) * 100)}%</Pill>}
          {c.severity === 'high' && <Pill tone="ember">high</Pill>}
          {c.assigned_name
            ? <Pill tone={active ? 'dark' : 'leaf'}>{c.assigned_name}</Pill>
            : <Pill tone={active ? 'dark' : 'ochre'}>unassigned</Pill>}
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

function CaseView({ id, onBack, onResolved }: { id: number; onBack: () => void; onResolved: () => void }) {
  const bundle = useAsync(() => api.caseBundle(id), [id])
  if (bundle.loading && !bundle.data) return <CaseSkeleton />
  if (bundle.error) return <ErrorBox error={bundle.error} onRetry={bundle.reload} />
  return <CaseDetail key={id} b={bundle.data!} onBack={onBack} onResolved={() => { bundle.reload(); onResolved() }} />
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

function QueueSkeleton() {
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

function CaseDetail({ b, onBack, onResolved }: { b: CaseBundle; onBack: () => void; onResolved: () => void }) {
  const timer = useElapsed()
  const [photo, setPhoto] = useState(0)
  const [showCam, setShowCam] = useState(true)
  const open = b.case.status === 'open'
  const top = b.model.hypotheses[0]

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="md:hidden flex items-center gap-1 text-sm text-soil-dark/60">
        <ArrowLeft className="w-4 h-4" /> Queue
      </button>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-instrument-serif text-3xl leading-tight">Case #{b.case.id}</h1>
          <p className="text-sm text-soil-dark/60 flex items-center gap-1">
            <MapPin className="w-3.5 h-3.5" />
            {b.farm.farmer_name} · {b.farm.crop_name} · {b.farm.district} · {b.farm.stage_name} ({b.farm.das} days) · {b.farm.area_acres} acres
          </p>
        </div>
        <div className="flex items-center gap-2">
          {open && <HandOff b={b} onDone={onResolved} />}
          {open && (
            <span className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium ${timer.s > 180 ? 'bg-ember/10 text-ember' : 'bg-leaf/10 text-leaf-deep'}`}>
              <Timer className="w-4 h-4" /> {timer.label} <span className="text-xs opacity-70">/ 3:00 target</span>
            </span>
          )}
        </div>
      </div>

      <div className="grid lg:grid-cols-[1.1fr_1fr] gap-4">
        <Card className="p-3">
          {b.photos.length > 0 ? (
            <>
              <div className="relative w-full aspect-[4/3] rounded-xl overflow-hidden">
                <img src={b.photos[photo]} alt="" className="w-full h-full object-cover" />
                {showCam && b.heatmaps?.[photo] && <GradCamOverlay heatmap={b.heatmaps[photo]!} />}
                {b.heatmaps?.[photo] && (
                  <button onClick={() => setShowCam((v) => !v)}
                    className="absolute bottom-2 left-2 bg-black/60 text-cream text-[11px] px-2.5 py-1 rounded-full">
                    {showCam ? 'Hide' : 'Show'} where the AI looked · Grad-CAM
                  </button>
                )}
              </div>
              {b.photos.length > 1 && (
                <div className="mt-2 flex gap-2">
                  {b.photos.map((p, i) => (
                    <button key={p} onClick={() => setPhoto(i)} className={`w-14 h-14 rounded-lg overflow-hidden ring-2 ${i === photo ? 'ring-ochre' : 'ring-transparent'}`}>
                      <img src={p} alt="" className="w-full h-full object-cover" />
                    </button>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="aspect-[4/3] rounded-xl bg-cream flex items-center justify-center text-sm text-soil-dark/50">No photo — raised from a field alert</div>
          )}
        </Card>

        <div className="space-y-3">
          <Card className="p-4">
            <h2 className="text-sm font-semibold">Model hypotheses</h2>
            <div className="mt-1 flex flex-wrap gap-1">
              <Pill tone="sky">Here because: {REASON_LABEL[b.case.reason] ?? b.case.reason}</Pill>
              {b.model.is_stub && <Pill tone="ochre">stub model</Pill>}
            </div>
            {b.model.hypotheses.length === 0 ? (
              <p className="mt-2 text-sm text-soil-dark/50">No model output for this case.</p>
            ) : (
              <ul className="mt-3 space-y-2">
                {b.model.hypotheses.map((h, i) => (
                  <li key={h.id}>
                    <div className="flex justify-between text-sm">
                      <span className={i === 0 ? 'font-semibold' : ''}>{h.name}</span>
                      <span className="text-soil-dark/60">{Math.round((h.confidence ?? 0) * 100)}%</span>
                    </div>
                    <div className="h-1.5 mt-1 rounded-full bg-soil-dark/10 overflow-hidden">
                      <div className={`h-full ${i === 0 ? 'bg-leaf' : 'bg-soil-dark/30'}`} style={{ width: `${Math.round((h.confidence ?? 0) * 100)}%` }} />
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-2 text-[11px] text-soil-dark/40">{b.model.version}</p>
          </Card>

          {b.doubt_doctor.length > 0 && (
            <Card className="p-4">
              <h2 className="text-sm font-semibold flex items-center gap-1.5"><HelpCircle className="w-4 h-4 text-ochre" /> Farmer's field answer</h2>
              {b.doubt_doctor.map((d, i) => (
                <div key={i} className="mt-2 text-sm">
                  <p className="text-soil-dark/70">"{d.question}"</p>
                  <p className="mt-1 font-semibold">→ {d.answer === 'unknown' ? "Can't tell" : d.answer.toUpperCase()}</p>
                </div>
              ))}
            </Card>
          )}
        </div>
      </div>

      <div className="grid md:grid-cols-3 gap-3">
        <Card className="p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-soil-dark/50">Trap counts</h3>
          {b.trap_readings.length === 0 ? <p className="mt-2 text-sm text-soil-dark/40">None recorded</p> : (
            <ul className="mt-2 space-y-1 text-sm">
              {b.trap_readings.slice(0, 5).map((t, i) => (
                <li key={i} className="flex justify-between"><span className="flex items-center gap-1"><Bug className="w-3 h-3" />{t.recorded_on}</span><span className={t.per_trap_night >= 8 ? 'text-ember font-semibold' : ''}>{t.per_trap_night}/trap/night</span></li>
              ))}
            </ul>
          )}
        </Card>
        <Card className="p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-soil-dark/50">Recent alerts on this farm</h3>
          {b.recent_alerts.length === 0 ? <p className="mt-2 text-sm text-soil-dark/40">None</p> : (
            <ul className="mt-2 space-y-1 text-sm">
              {b.recent_alerts.slice(0, 5).map((a) => (
                <li key={a.id} className="flex justify-between gap-2"><span className="truncate">{a.name}</span><span className="text-xs text-soil-dark/50 shrink-0">{a.trigger} · {a.outcome ?? 'open'}</span></li>
              ))}
            </ul>
          )}
        </Card>
        <Card className="p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-soil-dark/50">Farm history & follow-ups</h3>
          <ul className="mt-2 space-y-1 text-sm">
            {b.farm_history.map((h, i) => <li key={i}>{h.final_label.replace(/_/g, ' ')} · {h.verdict}</li>)}
            {b.followups.map((f, i) => <li key={`f${i}`} className="text-soil-dark/70">Follow-up {f.due_on}: {f.response ?? 'pending'}</li>)}
            {b.farm_history.length === 0 && b.followups.length === 0 && <li className="text-soil-dark/40">First problem on record</li>}
          </ul>
        </Card>
      </div>

      {b.satellite && <SatelliteEvidence s={b.satellite} />}

      {b.icar_referral?.length > 0 && <IcarReferral b={b} />}

      {open ? <Decision b={b} top={top?.id} elapsed={timer.s} onResolved={onResolved} /> : (
        <Card className="p-4 flex items-center gap-2 text-leaf-deep"><CheckCircle2 className="w-5 h-5" /> Resolved</Card>
      )}
    </div>
  )
}

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
      <Card className="p-5 border-leaf/40 bg-leaf/5">
        <p className="flex items-center gap-2 font-semibold text-leaf-deep"><CheckCircle2 className="w-5 h-5" /> {done.verdict === 'confirmed' ? 'Confirmed' : 'Corrected'} in {Math.floor(done.secs / 60)}:{String(done.secs % 60).padStart(2, '0')}</p>
        <ul className="mt-2 text-sm space-y-1 text-soil-dark/80">
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
    <Card className="p-4 space-y-3 border-leaf/30">
      <h2 className="font-semibold">Your decision</h2>
      <div className="grid md:grid-cols-2 gap-3">
        <label className="block text-xs text-soil-dark/60">
          Final diagnosis
          <select value={label} onChange={(e) => setLabel(e.target.value)} className="mt-1 w-full min-h-[44px] rounded-xl border border-soil-dark/20 px-3 bg-cream/50 text-sm">
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
        <label className="block text-xs text-soil-dark/60">
          Reviewing expert
          <input value={name} readOnly aria-readonly className="mt-1 w-full min-h-[44px] rounded-xl border border-soil-dark/10 px-3 bg-soil-dark/5 text-sm" />
        </label>
      </div>
      <label className="block text-xs text-soil-dark/60">
        {label === 'other' ? 'What is it? (required — the farmer is shown this)' : 'Note to farmer (optional)'}
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2}
          placeholder={label === 'other' ? 'Name the problem, e.g. "Zinc deficiency — interveinal chlorosis on older leaves"' : undefined}
          className={`mt-1 w-full rounded-xl border px-3 py-2 bg-cream/50 text-sm ${
            label === 'other' && !notes.trim() ? 'border-ember/50' : 'border-soil-dark/20'}`} />
      </label>
      {label === 'healthy' && (
        <p className="text-xs rounded-xl bg-leaf/10 text-leaf-deep p-2.5">
          Recorded as healthy: no advisory, no spread alert, and the model's guess is marked wrong.
        </p>
      )}
      {label === 'other' && (
        <p className="text-xs rounded-xl bg-ochre/10 text-[#8a5a17] p-2.5">
          Outside the knowledge base, so the app offers no treatment of its own — the farmer sees your
          note and the referral. It is logged as a gap for the team.
        </p>
      )}
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={lab} onChange={(e) => setLab(e.target.checked)} className="w-4 h-4 accent-leaf-deep" />
        <FlaskRound className="w-4 h-4 text-soil-dark/60" /> Refer sample to a diagnostic lab / KVK
      </label>
      {error && <ErrorBox error={error} />}
      <button onClick={submit} disabled={busy || !label || !name.trim() || (label === 'other' && !notes.trim())}
        className="w-full min-h-[48px] rounded-full bg-leaf-deep text-cream text-sm font-medium flex items-center justify-center gap-2 disabled:opacity-50">
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
    <Card className="p-4">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-soil-dark/50">ICAR technologies &amp; referral</h3>
      <p className="text-[11px] text-soil-dark/50 mt-0.5">From the ICAR technology repository, matched to the suspected problems, then crop-level tools.</p>
      <ul className="mt-3 grid md:grid-cols-2 gap-2">
        {b.icar_referral.map((x) => (
          <li key={x.id} className="rounded-xl border border-soil-dark/10 p-3 text-sm">
            <div className="flex flex-wrap gap-1">
              <Pill tone="leaf">{ICAR_TYPE[x.type]}</Pill>
              <Pill>{x.for_target ? `for ${names[x.for_target] ?? x.for_target}` : `${b.farm.crop_name} (crop-level)`}</Pill>
            </div>
            <p className="mt-1.5 font-medium leading-snug">{x.source_name}</p>
            <p className="mt-1 text-[13px] text-soil-dark/70 leading-snug">{x.summary}</p>
            {x.claim && <p className="mt-1 text-xs text-leaf-deep">{x.claim}</p>}
            {x.lead_time_days && <p className="mt-1 text-xs text-[#8a5a17]">Needs {x.lead_time_days} days' notice to the institute.</p>}
            <p className="mt-1.5 text-xs text-soil-dark/60">
              {x.institute.name}, {x.institute.city} · <a className="text-leaf-deep" href={`tel:${(x.institute.phone ?? '').replace(/[^0-9+]/g, '')}`}>{x.institute.phone}</a>
              {x.institute.email && <> · <span title={x.institute.email_note}>{x.institute.email}{x.institute.email_note ? ' (unverified)' : ''}</span></>}
            </p>
          </li>
        ))}
      </ul>
    </Card>
  )
}
