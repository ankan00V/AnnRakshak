import { useEffect, useMemo, useState } from 'react'
import {
  ArrowLeft, Bug, CheckCircle2, ClipboardList, FlaskRound, HelpCircle, Inbox, Loader2, MapPin, Send, Timer, UserCheck,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { CaseBundle, CaseListItem } from '../api/types'
import { useAsync } from '../lib/hooks'
import { useAuth } from '../auth/AuthContext'
import { Card, ErrorBox, GradCamOverlay, Pill, Spinner } from '../ui/kit'
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
  const list = useAsync(() => api.cases(tab), [tab])
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
          {list.loading && !list.data && <Spinner />}
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
  if (bundle.loading && !bundle.data) return <Spinner />
  if (bundle.error) return <ErrorBox error={bundle.error} onRetry={bundle.reload} />
  return <CaseDetail key={id} b={bundle.data!} onBack={onBack} onResolved={() => { bundle.reload(); onResolved() }} />
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
        {open && (
          <span className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium ${timer.s > 180 ? 'bg-ember/10 text-ember' : 'bg-leaf/10 text-leaf-deep'}`}>
            <Timer className="w-4 h-4" /> {timer.label} <span className="text-xs opacity-70">/ 3:00 target</span>
          </span>
        )}
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
  const [done, setDone] = useState<{ verdict: string; spread: number; secs: number } | null>(null)
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
      setDone({ verdict: r.verdict, spread: r.spread_alerts, secs: elapsed })
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
          <li>• The farmer now sees the expert-confirmed advisory in their language.</li>
          <li>• {done.spread} nearby {b.farm.crop} farm{done.spread === 1 ? '' : 's'} within 5 km received an inspection alert.</li>
          <li>• District confirmation counts updated — this is how the system learns from field confirmations.</li>
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
          </select>
        </label>
        <label className="block text-xs text-soil-dark/60">
          Reviewing expert
          <input value={name} readOnly aria-readonly className="mt-1 w-full min-h-[44px] rounded-xl border border-soil-dark/10 px-3 bg-soil-dark/5 text-sm" />
        </label>
      </div>
      <label className="block text-xs text-soil-dark/60">
        Note to farmer (optional)
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} className="mt-1 w-full rounded-xl border border-soil-dark/20 px-3 py-2 bg-cream/50 text-sm" />
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={lab} onChange={(e) => setLab(e.target.checked)} className="w-4 h-4 accent-leaf-deep" />
        <FlaskRound className="w-4 h-4 text-soil-dark/60" /> Refer sample to a diagnostic lab / KVK
      </label>
      {error && <ErrorBox error={error} />}
      <button onClick={submit} disabled={busy || !label || !name.trim()}
        className="w-full min-h-[48px] rounded-full bg-leaf-deep text-cream text-sm font-medium flex items-center justify-center gap-2 disabled:opacity-50">
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
        {label === top ? 'Confirm model diagnosis' : 'Correct and send'}
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
