import { useEffect, useRef, useState } from 'react'
import {
  ArrowLeft, ArrowRightLeft, Camera, CheckCircle2, Clock, FlaskConical, HelpCircle, Loader2, PhoneCall, Plus, RefreshCw, ShieldQuestion, UserRound,
} from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import type { CaseBrief, DiagnoseResult, Farm, TargetView } from '../../api/types'
import { useAsync } from '../../lib/hooks'
import { ConfidenceMeter, GradCamOverlay, ListenButton, Pill } from '../../ui/kit'
import AdvisoryView from '../components/AdvisoryView'
import { useFarmer } from '../FarmerContext'
import { bcp47 } from '../../lib/i18n'

export default function Result() {
  const { result, t } = useFarmer()
  if (!result) {
    return (
      <div className="text-center pt-16">
        <p className="text-sm text-soil-dark/60">{t('noProblems')}</p>
        <Link to="/app/scan" className="mt-6 inline-flex items-center min-h-[48px] px-6 rounded-full bg-leaf-deep text-cream text-sm font-medium">
          <Camera className="w-4 h-4 mr-2" />
          {t('takePhoto')}
        </Link>
      </div>
    )
  }
  return <ResultView r={result} />
}

function ResultView({ r }: { r: DiagnoseResult }) {
  const { t, lang, setResult } = useFarmer()
  const navigate = useNavigate()
  const outcome = r.gate.outcome
  const top = r.gate.alternatives[0]
  const [escalating, setEscalating] = useState(false)

  // Language switched on this screen: the same result, re-rendered in the new language.
  const langSeen = useRef(lang)
  useEffect(() => {
    if (langSeen.current === lang) return
    langSeen.current = lang
    let on = true
    api.problemResult(r.problem_id, lang).then((fresh) => on && setResult({ ...r, ...fresh })).catch(() => undefined)
    return () => {
      on = false
    }
  }, [lang, r, setResult])

  const askExpert = async () => {
    setEscalating(true)
    try {
      const out = await api.escalate(r.problem_id, lang)
      setResult({ ...r, gate: { ...r.gate, outcome: 'escalate', reason: 'FARMER_REQUEST' }, case: out.case, advisory: undefined, message: out.message })
    } finally {
      setEscalating(false)
    }
  }

  return (
    <div className="space-y-5">
      <button onClick={() => navigate('/app')} className="flex items-center gap-1 text-sm text-soil-dark/60">
        <ArrowLeft className="w-4 h-4" />
        {t('back')}
      </button>

      <div className="relative aspect-square rounded-3xl overflow-hidden bg-soil-dark">
        {r.image_url && <img src={r.image_url} alt="" className="w-full h-full object-cover" />}
        {r.heatmap && outcome !== 'retake' && <GradCamOverlay heatmap={r.heatmap} />}
        {r.heatmap && outcome !== 'retake' && (
          <span className="absolute bottom-3 left-3 bg-black/60 text-cream text-[11px] px-2.5 py-1 rounded-full">
            {t('aiLookedHere')} · Grad-CAM
          </span>
        )}
        {r.is_stub && (
          <span className="absolute top-3 inset-x-3 bg-ochre text-cream text-[11px] font-medium px-3 py-2 rounded-xl shadow">
            {t('demoModel')}
          </span>
        )}
      </div>

      {outcome === 'advise' && r.healthy_note && (
        <section className="rounded-2xl bg-leaf/10 border border-leaf/30 p-4">
          <h1 className="font-instrument-serif text-3xl text-leaf-deep flex items-center gap-2">
            <CheckCircle2 className="w-6 h-6" />
            {t('healthyTitle')}
          </h1>
          <p className="mt-1 text-sm">{r.healthy_note}</p>
        </section>
      )}

      {outcome === 'advise' && r.advisory && (
        <>
          <Diagnosis name={r.advisory.name} signature={r.advisory.signature} confidence={top.confidence ?? r.gate.confidence} r={r} />
          <AdvisoryView advisory={r.advisory} />
          {r.followup && (
            <p className="text-xs text-soil-dark/60 flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5" />
              {t('followupScheduled')} {new Date(r.followup.due_on).toLocaleDateString(bcp47(lang), { day: 'numeric', month: 'long' })}
            </p>
          )}
          <div className="grid grid-cols-1 gap-2">
            <Link to="/app/spray" className="min-h-[48px] rounded-full bg-ochre text-cream flex items-center justify-center gap-2 text-sm font-medium">
              <FlaskConical className="w-4 h-4" />
              {t('checkBottle')}
            </Link>
            <button onClick={askExpert} disabled={escalating} className="min-h-[48px] rounded-full border border-soil-dark/25 text-sm font-medium flex items-center justify-center gap-2">
              {escalating ? <Loader2 className="w-4 h-4 animate-spin" /> : <UserRound className="w-4 h-4" />}
              {t('askExpert')}
            </button>
          </div>
        </>
      )}

      {outcome === 'clarify' && r.clarify && <DoubtDoctor r={r} />}

      {outcome === 'escalate' && r.gate.reason === 'CROP_MISMATCH' && top && (top.confidence ?? 0) >= 0.6 && <CropMismatch r={r} top={top} />}

      {outcome === 'escalate' && <Escalated message={r.message} kase={r.case} alternatives={r.gate.alternatives} />}

      {outcome === 'retake' && (
        <section className="rounded-2xl bg-white border border-soil-dark/10 p-5 text-center">
          <RefreshCw className="w-8 h-8 mx-auto text-ochre" />
          <h1 className="mt-2 font-instrument-serif text-2xl">{t('retakeTitle')}</h1>
          <p className="mt-1 text-sm text-soil-dark/70">{r.message}</p>
          <p className="mt-3 text-xs text-soil-dark/50">{t('retakeTips')}</p>
          <Link to="/app/scan" className="mt-4 inline-flex items-center min-h-[48px] px-6 rounded-full bg-leaf-deep text-cream text-sm font-medium">
            <Camera className="w-4 h-4 mr-2" />
            {t('tryAgain')}
          </Link>
        </section>
      )}
    </div>
  )
}

function Diagnosis({ name, signature, confidence, r }: { name: string; signature: string; confidence: number; r: DiagnoseResult }) {
  const { t } = useFarmer()
  return (
    <section className="rounded-2xl bg-white border border-soil-dark/10 p-4 space-y-3">
      <div>
        <h1 className="font-instrument-serif text-3xl leading-tight">{name}</h1>
        <p className="text-sm text-soil-dark/70 mt-1">{signature}</p>
      </div>
      {r.resolved_by ? (
        <div className="rounded-xl bg-ochre/10 border border-ochre/30 p-3">
          <p className="text-xs font-semibold text-[#8a5a17] flex items-center gap-1.5">
            <HelpCircle className="w-3.5 h-3.5" />
            {t('advisedByDoubt')}
          </p>
          <p className="mt-1 text-[13px] text-soil-dark/80">"{r.resolved_by.question}" → <b>{r.resolved_by.answer}</b></p>
        </div>
      ) : (
        <ConfidenceMeter value={confidence} label={t('confidence')} askLabel={t('meterAsk')} adviseLabel={t('meterAdvise')} />
      )}
      {r.prior_bias && Object.keys(r.prior_bias).length > 0 && (
        <p className="text-[11px] text-soil-dark/50">{t('learnedNote')}</p>
      )}
      <Alternatives alts={r.gate.alternatives.slice(1)} />
    </section>
  )
}

function Alternatives({ alts }: { alts: TargetView[] }) {
  const { t } = useFarmer()
  if (alts.length === 0) return null
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-soil-dark/50">{t('otherPossibilities')}</p>
      <ul className="mt-1 space-y-1">
        {alts.map((a) => (
          <li key={a.id} className="flex items-center gap-2 text-xs">
            <span className="flex-1 truncate">{a.name}</span>
            <span className="w-24 h-1.5 rounded-full bg-soil-dark/10 overflow-hidden">
              <span className="block h-full bg-soil-dark/30" style={{ width: `${Math.round((a.confidence ?? 0) * 100)}%` }} />
            </span>
            <span className="w-9 text-right text-soil-dark/60">{Math.round((a.confidence ?? 0) * 100)}%</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** The model is torn between two labels: show both, ask one physical question
 *  authored in the knowledge base. "Can't tell" escalates — never a coin flip. */
function DoubtDoctor({ r }: { r: DiagnoseResult }) {
  const { t, lang, setResult } = useFarmer()
  const [busy, setBusy] = useState<string | null>(null)
  const c = r.clarify!

  const answer = async (a: 'yes' | 'no' | 'unknown') => {
    setBusy(a)
    try {
      const out = await api.clarify(r.problem_id, c.cue_id, a, lang)
      if (out.outcome === 'advise' && out.advisory) {
        const resolved = r.gate.alternatives.find((x) => x.id === out.resolved_target) ?? r.gate.alternatives[0]
        setResult({
          ...r,
          gate: { ...r.gate, outcome: 'advise', alternatives: [resolved, ...r.gate.alternatives.filter((x) => x.id !== resolved.id)] },
          advisory: out.advisory,
          followup: out.followup,
          clarify: undefined,
          resolved_by: { question: c.question, answer: a === 'yes' ? t('yes') : t('no') },
        })
      } else {
        setResult({ ...r, gate: { ...r.gate, outcome: 'escalate' }, case: out.case, message: out.message ?? '', clarify: undefined })
      }
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="space-y-4">
      <div className="rounded-2xl bg-ochre/10 border border-ochre/40 p-4">
        <p className="flex items-center gap-2 text-sm font-semibold text-[#8a5a17]">
          <ShieldQuestion className="w-5 h-5" />
          {t('twoPossibilities')}
        </p>
        <div className="mt-3 grid grid-cols-2 gap-2">
          {c.candidates.map((cand) => {
            const conf = r.gate.alternatives.find((a) => a.id === cand.id)?.confidence ?? 0
            return (
              <div key={cand.id} className="rounded-xl bg-white p-3 border border-soil-dark/10">
                <p className="text-sm font-semibold leading-tight">{cand.name}</p>
                <p className="text-[11px] text-soil-dark/50 mt-0.5">{Math.round(conf * 100)}%</p>
                <p className="text-[12px] leading-snug text-soil-dark/70 mt-1.5">{cand.signature}</p>
              </div>
            )
          })}
        </div>
      </div>

      <div className="rounded-2xl bg-leaf-deep text-cream p-5">
        <div className="flex items-start justify-between gap-3">
          <p className="text-xs uppercase tracking-wide text-cream/60 flex items-center gap-1.5">
            <HelpCircle className="w-4 h-4" />
            {t('oneQuestion')}
          </p>
          <ListenButton text={c.question} lang={lang} label={t('listen')} stopLabel={t('stop')} compact tone="light" />
        </div>
        <p className="mt-2 text-lg leading-snug font-medium">{c.question}</p>
        <div className="mt-4 grid grid-cols-3 gap-2">
          {([['yes', t('yes'), 'bg-cream text-leaf-deep'], ['no', t('no'), 'bg-cream text-leaf-deep'], ['unknown', t('cantTell'), 'bg-cream/10 text-cream border border-cream/30']] as const).map(([a, label, cls]) => (
            <button key={a} onClick={() => answer(a)} disabled={busy !== null} className={`min-h-[52px] rounded-xl text-sm font-semibold ${cls}`}>
              {busy === a ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : label}
            </button>
          ))}
        </div>
      </div>
    </section>
  )
}

function Escalated({ message, kase, alternatives }: { message: string; kase?: CaseBrief; alternatives: TargetView[] }) {
  const { t } = useFarmer()
  return (
    <section className="space-y-3">
      <div className="rounded-2xl bg-sky-50 border border-sky-200 p-5">
        <UserRound className="w-8 h-8 text-sky-700" />
        <h1 className="mt-2 font-instrument-serif text-2xl leading-tight">{t('sentToExpert')}</h1>
        <p className="mt-1 text-sm text-soil-dark/80">{message}</p>
        <p className="mt-2 text-sm font-medium text-ember">{t('sentToExpertSub')}</p>
        {kase && kase.status === 'open' && (
          <div className="mt-4 grid grid-cols-2 gap-2">
            <div className="rounded-xl bg-white p-3">
              <p className="text-[11px] text-soil-dark/50">{t('queuePosition')}</p>
              <p className="text-2xl font-semibold">#{kase.queue_position}</p>
            </div>
            <div className="rounded-xl bg-white p-3">
              <p className="text-[11px] text-soil-dark/50">{t('eta')}</p>
              <p className="text-2xl font-semibold">{kase.eta_minutes} <span className="text-sm font-normal">{t('minutes')}</span></p>
            </div>
          </div>
        )}
      </div>
      {alternatives.length > 0 && (
        <div className="rounded-2xl bg-white border border-soil-dark/10 p-4">
          <Alternatives alts={alternatives} />
        </div>
      )}
      <a href="tel:18001801551" className="flex items-center justify-center gap-2 min-h-[48px] rounded-full border border-soil-dark/20 text-sm font-medium bg-white">
        <PhoneCall className="w-4 h-4" />
        {t('callKcc')}
      </a>
      <Pill className="mx-auto">{kase ? `Case #${kase.id}` : ''}</Pill>
    </section>
  )
}

/** The photo shows another crop than the farm is registered for. Say what the
 *  model sees, and let the farmer re-check the same photo on a farm of that crop. */
function CropMismatch({ r, top }: { r: DiagnoseResult; top: TargetView }) {
  const { t, lang, farmId, setFarmId, setResult } = useFarmer()
  const navigate = useNavigate()
  const farms = useAsync(() => api.farms(lang), [lang], ['farms', lang].join(':'))
  const crops = useAsync(() => api.crops(lang), [lang], ['crops', lang].join(':'))
  const [busy, setBusy] = useState<number | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const cropName = crops.data?.find((c) => c.id === top.crop)?.name ?? top.crop
  const others: Farm[] = (farms.data ?? []).filter((f) => f.crop === top.crop).slice(0, 4)
  const mine = (farms.data ?? []).find((x) => x.id === farmId) ?? farms.data?.[0]
  const [adding, setAdding] = useState(false)
  const [sowing, setSowing] = useState(() => new Date(Date.now() - 30 * 864e5).toISOString().slice(0, 10))
  const [area, setArea] = useState('1')

  /** The farmer grows this crop too, on another plot: register it from here,
   *  copying the village and language from the field they are standing in, and
   *  check the same photo on it straight away. */
  const addAndCheck = async () => {
    if (!mine || !r.image_url) return
    setBusy(-1)
    setErr(null)
    try {
      const farm = await api.createFarm({
        farmer_name: mine.farmer_name, lang: mine.lang, crop: top.crop, sowing_date: sowing,
        district: mine.district, village: mine.village, lat: mine.lat, lon: mine.lon,
        area_acres: parseFloat(area) || 1,
      })
      await recheck(farm)
    } catch (e) {
      setErr((e as Error).message)
      setBusy(null)
    }
  }

  const recheck = async (f: Farm) => {
    if (!r.image_url) return
    setBusy(f.id)
    setErr(null)
    try {
      const blob = await (await fetch(r.image_url)).blob()
      const out = await api.diagnose(f.id, blob, f.lang)  // that farm's own language: the app switches to it
      setFarmId(f.id)
      setResult(out)
      navigate('/app/result')
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="rounded-2xl bg-ochre/10 border border-ochre/40 p-5">
      <ArrowRightLeft className="w-7 h-7 text-[#8a5a17]" />
      <h1 className="mt-2 font-instrument-serif text-2xl leading-tight">{t('mismatchTitle').replace('{crop}', cropName)}</h1>
      <p className="mt-1 text-sm text-soil-dark/80">
        {t('mismatchBody').replace('{name}', top.name).replace('{crop}', cropName)
          .replace('{pct}', String(Math.round((top.confidence ?? 0) * 100)))}
      </p>
      {others.length > 0 && (
        <>
          <p className="mt-3 text-xs font-medium text-soil-dark/70">{t('mismatchPick').replace('{crop}', cropName)}</p>
          <div className="mt-2 grid gap-2">
            {others.map((f) => (
              <button key={f.id} onClick={() => recheck(f)} disabled={busy !== null}
                className="flex items-center justify-between gap-2 min-h-[48px] rounded-xl bg-white border border-soil-dark/10 px-3 text-sm text-left disabled:opacity-60">
                <span><span className="font-medium">{f.farmer_name}</span> <span className="text-xs text-soil-dark/55">· {f.district}</span></span>
                {busy === f.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <span className="text-leaf-deep text-xs font-medium">{t('mismatchCheck')} →</span>}
              </button>
            ))}
          </div>
        </>
      )}
      {others.length === 0 && !adding && (
        <button onClick={() => setAdding(true)}
          className="mt-3 w-full min-h-[48px] rounded-full bg-leaf-deep text-cream text-sm font-semibold flex items-center justify-center gap-2">
          <Plus className="w-4 h-4" />
          {t('mismatchAddField').replace('{crop}', cropName)}
        </button>
      )}
      {adding && (
        <div className="mt-3 rounded-2xl bg-white border border-soil-dark/10 p-3 space-y-3">
          <p className="text-[13px] font-semibold">{t('mismatchNewField').replace('{crop}', cropName)}</p>
          <label className="block text-xs text-soil-dark/60">
            {t('sowingDate')}
            <input type="date" value={sowing} max={new Date().toISOString().slice(0, 10)}
              onChange={(e) => setSowing(e.target.value)}
              className="mt-1 w-full min-h-[44px] rounded-xl border border-soil-dark/20 px-3 bg-cream/50 text-sm" />
          </label>
          <label className="block text-xs text-soil-dark/60">
            {t('area')}
            <input type="number" inputMode="decimal" min="0.1" step="0.1" value={area}
              onChange={(e) => setArea(e.target.value)}
              className="mt-1 w-full min-h-[44px] rounded-xl border border-soil-dark/20 px-3 bg-cream/50 text-sm" />
          </label>
          <button onClick={addAndCheck} disabled={busy !== null || !(parseFloat(area) > 0)}
            className="w-full min-h-[48px] rounded-full bg-leaf-deep text-cream text-sm font-semibold flex items-center justify-center gap-2 disabled:opacity-50">
            {busy !== null ? <Loader2 className="w-4 h-4 animate-spin" /> : <Camera className="w-4 h-4" />}
            {t('mismatchAddAndCheck')}
          </button>
        </div>
      )}
      {err && <p className="mt-2 text-xs text-ember">{err}</p>}
    </section>
  )
}
