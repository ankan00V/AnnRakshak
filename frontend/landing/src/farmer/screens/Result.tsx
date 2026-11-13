import { useEffect, useRef, useState } from 'react'
import {
  AlertTriangle, ArrowLeft, ArrowRightLeft, Camera, CheckCircle2, Clock, FlaskConical, HelpCircle, Loader2, PhoneCall, Plus, RefreshCw, ShieldQuestion, UserRound,
} from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import type { CaseBrief, DiagnoseResult, Farm, TargetView } from '../../api/types'
import { useAsync } from '../../lib/hooks'
import { ConfidenceMeter, ErrorBox, GradCamOverlay, ListenButton } from '../../ui/kit'
import AdvisoryView from '../components/AdvisoryView'
import { useFarmer } from '../FarmerContext'
import { bcp47 } from '../../lib/i18n'
import { FIELD, LABEL, PANEL, PRIMARY, SECONDARY } from '../tokens'
import { PanelHead } from '../ui'

export default function Result() {
  const { result, t } = useFarmer()
  if (!result) {
    return (
      <section className={`${PANEL} mx-auto max-w-xl p-8 text-center`}>
        <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-[#e3efd9] text-[#2f6a39]">
          <Camera className="h-7 w-7" aria-hidden />
        </span>
        <p className="mt-4 text-[16px] text-soil-dark/80">{t('noProblems')}</p>
        <Link to="/app/scan" className={`${PRIMARY.replace('w-full', 'w-auto')} mx-auto mt-6 inline-flex px-7`}>
          <Camera className="h-5 w-5" aria-hidden /> {t('takePhoto')}
        </Link>
      </section>
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
  const [askFailed, setAskFailed] = useState<Error | null>(null)

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
    setAskFailed(null)
    try {
      const out = await api.escalate(r.problem_id, lang)
      setResult({ ...r, gate: { ...r.gate, outcome: 'escalate', reason: 'FARMER_REQUEST' }, case: out.case, advisory: undefined, message: out.message })
    } catch (e) {
      // Silence here reads as "sent": the farmer waits for an expert who was
      // never asked. They are told, and the button is still there.
      setAskFailed(e as Error)
    } finally {
      setEscalating(false)
    }
  }

  const advise = outcome === 'advise'
  return (
    <div className="space-y-5">
      <button onClick={() => navigate('/app')} className="inline-flex min-h-[44px] items-center gap-1.5 text-[15px] font-medium text-leaf-deep">
        <ArrowLeft className="h-5 w-5" aria-hidden />
        {t('back')}
      </button>

      {/* The photo and what it is on the left; what to do about it, which is
          the long part, beside it. */}
      <div className="grid gap-6 lg:grid-cols-[380px_minmax(0,1fr)] xl:grid-cols-[420px_minmax(0,1fr)]">
        <div className="min-w-0 space-y-6">
          <section className={`${PANEL} p-2`}>
            {/* Square: the heatmap is drawn over the whole frame and must sit on
                the same pixels the model looked at. */}
            <div className="relative aspect-square overflow-hidden rounded-[22px] bg-leaf-deep">
              {r.image_url && <img src={r.image_url} alt="" className="h-full w-full object-cover" />}
              {r.heatmap && outcome !== 'retake' && <GradCamOverlay heatmap={r.heatmap} />}
              {r.heatmap && outcome !== 'retake' && (
                <span className="absolute bottom-3 left-3 rounded-full bg-black/60 px-3 py-1 text-[12px] text-white">
                  {t('aiLookedHere')}
                </span>
              )}
              {r.is_stub && (
                <span className="absolute inset-x-3 top-3 rounded-2xl bg-ochre px-3 py-2 text-[13px] font-medium text-white shadow">
                  {t('demoModel')}
                </span>
              )}
            </div>
            {advise && r.healthy_note && (
              <div className="mx-1 mb-1 mt-3 rounded-[20px] bg-[#f1f6ec] p-4">
                <h1 className="flex items-center gap-2 font-instrument-serif text-[30px] leading-tight text-leaf-deep">
                  <CheckCircle2 className="h-7 w-7 shrink-0" aria-hidden />
                  {t('healthyTitle')}
                </h1>
                <p className="mt-1 text-[15px]">{r.healthy_note}</p>
              </div>
            )}
            {advise && r.advisory && (
              <Diagnosis name={r.advisory.name} signature={r.advisory.signature} confidence={top.confidence ?? r.gate.confidence} r={r} />
            )}
          </section>

          {advise && r.advisory && (
            <section className={`${PANEL} space-y-3 p-5`}>
              {r.followup && (
                <p className="flex items-center gap-2 rounded-[18px] bg-[#f5f7f1] p-3.5 text-[14px] text-soil-dark/85">
                  <Clock className="h-5 w-5 shrink-0 text-leaf-deep" aria-hidden />
                  {t('followupScheduled')} {new Date(r.followup.due_on).toLocaleDateString(bcp47(lang), { day: 'numeric', month: 'long' })}
                </p>
              )}
              <Link to="/app/spray" className={PRIMARY}>
                <FlaskConical className="h-5 w-5" aria-hidden />
                {t('checkBottle')}
              </Link>
              <button onClick={askExpert} disabled={escalating} className={`${SECONDARY} w-full`}>
                {escalating ? <Loader2 className="h-5 w-5 animate-spin" /> : <UserRound className="h-5 w-5" aria-hidden />}
                {t('askExpert')}
              </button>
              {askFailed && <ErrorBox error={askFailed} onRetry={() => { void askExpert() }} retryLabel={t('retry')} />}
            </section>
          )}
        </div>

        <div className="min-w-0 space-y-6">
          {advise && r.advisory && <AdvisoryView advisory={r.advisory} />}

          {outcome === 'clarify' && r.clarify && <DoubtDoctor r={r} />}

          {outcome === 'escalate' && r.gate.reason === 'CROP_MISMATCH' && top && (top.confidence ?? 0) >= 0.6 && <CropMismatch r={r} top={top} />}

          {outcome === 'escalate' && <Escalated message={r.message} kase={r.case} alternatives={r.gate.alternatives} />}

          {outcome === 'retake' && (
            <section className={`${PANEL} p-6 text-center lg:p-8`}>
              <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-[#fbf0dc] text-[#8a5a17]">
                <RefreshCw className="h-7 w-7" aria-hidden />
              </span>
              <h1 className="mt-3 font-instrument-serif text-[30px] leading-tight">{t('retakeTitle')}</h1>
              <p className="mx-auto mt-2 max-w-md text-[15px] text-soil-dark/85">{r.message}</p>
              <p className="mx-auto mt-3 max-w-md rounded-[18px] bg-[#f5f7f1] p-3.5 text-[14px] text-soil-dark/80">{t('retakeTips')}</p>
              <Link to="/app/scan" className={`${PRIMARY.replace('w-full', 'w-auto')} mx-auto mt-5 inline-flex px-7`}>
                <Camera className="h-5 w-5" aria-hidden />
                {t('tryAgain')}
              </Link>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}

function Diagnosis({ name, signature, confidence, r }: { name: string; signature: string; confidence: number; r: DiagnoseResult }) {
  const { t } = useFarmer()
  return (
    <div className="space-y-4 px-3 pb-4 pt-4">
      <div>
        <h1 className="font-instrument-serif text-[34px] leading-tight text-balance lg:text-[38px]">{name}</h1>
        <p className="mt-1 text-[15px] leading-snug text-soil-dark/80">{signature}</p>
      </div>
      {r.resolved_by ? (
        <div className="rounded-[18px] bg-[#fbf0dc] p-3.5">
          <p className="flex items-center gap-1.5 text-[14px] font-semibold text-[#7a4f12]">
            <HelpCircle className="h-4 w-4" aria-hidden />
            {t('advisedByDoubt')}
          </p>
          <p className="mt-1 text-[14px] text-soil-dark/85">"{r.resolved_by.question}" → <b>{r.resolved_by.answer}</b></p>
        </div>
      ) : (
        <ConfidenceMeter value={confidence} label={t('confidence')} askLabel={t('meterAsk')} adviseLabel={t('meterAdvise')} />
      )}
      {r.prior_bias && Object.keys(r.prior_bias).length > 0 && (
        <p className="text-[13px] text-soil-dark/70">{t('learnedNote')}</p>
      )}
      <Alternatives alts={r.gate.alternatives.slice(1)} />
    </div>
  )
}

function Alternatives({ alts }: { alts: TargetView[] }) {
  const { t } = useFarmer()
  if (alts.length === 0) return null
  return (
    <div>
      <p className="text-[14px] font-semibold text-soil-dark/80">{t('otherPossibilities')}</p>
      <ul className="mt-2 space-y-2">
        {alts.map((a) => (
          <li key={a.id} className="flex items-center gap-3 text-[14px]">
            <span className="min-w-0 flex-1 truncate">{a.name}</span>
            <span className="h-2 w-24 overflow-hidden rounded-full bg-soil-dark/[0.08]">
              <span className="block h-full rounded-full bg-[#4b8b3b]/50" style={{ width: `${Math.round((a.confidence ?? 0) * 100)}%` }} />
            </span>
            <span className="w-10 text-right tabular-nums text-soil-dark/75">{Math.round((a.confidence ?? 0) * 100)}%</span>
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
  const [failed, setFailed] = useState<Error | null>(null)
  const c = r.clarify!

  const answer = async (a: 'yes' | 'no' | 'unknown') => {
    setBusy(a)
    setFailed(null)
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
    } catch (e) {
      // The farmer looked at their crop and answered. Losing that without a
      // word leaves the question on screen as though they never did.
      setFailed(e as Error)
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="space-y-6">
      <div className={`${PANEL} p-5 lg:p-6`}>
        <PanelHead icon={ShieldQuestion} title={t('twoPossibilities')} />
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {c.candidates.map((cand) => {
            const conf = r.gate.alternatives.find((a) => a.id === cand.id)?.confidence ?? 0
            return (
              <div key={cand.id} className="rounded-[20px] bg-[#f5f7f1] p-4">
                <p className="flex items-baseline justify-between gap-2">
                  <span className="text-[16px] font-semibold leading-tight">{cand.name}</span>
                  <span className="shrink-0 text-[14px] tabular-nums text-soil-dark/70">{Math.round(conf * 100)}%</span>
                </p>
                <p className="mt-2 text-[14px] leading-snug text-soil-dark/80">{cand.signature}</p>
              </div>
            )
          })}
        </div>
      </div>

      <div className="rounded-[28px] bg-[#1d4a2c] p-5 text-white lg:p-6">
        <div className="flex items-start justify-between gap-3">
          <p className="flex items-center gap-2 text-[15px] font-semibold text-white/85">
            <HelpCircle className="h-5 w-5" aria-hidden />
            {t('oneQuestion')}
          </p>
          <ListenButton text={c.question} lang={lang} label={t('listen')} stopLabel={t('stop')} compact tone="light" />
        </div>
        <p className="mt-3 text-[21px] font-medium leading-snug">{c.question}</p>
        <div className="mt-5 grid grid-cols-3 gap-2">
          {([['yes', t('yes'), 'bg-white text-[#1d4a2c]'], ['no', t('no'), 'bg-white text-[#1d4a2c]'], ['unknown', t('cantTell'), 'bg-white/10 text-white ring-1 ring-white/30']] as const).map(([a, label, cls]) => (
            <button key={a} onClick={() => answer(a)} disabled={busy !== null} className={`min-h-[56px] rounded-2xl text-[16px] font-semibold ${cls}`}>
              {busy === a ? <Loader2 className="mx-auto h-5 w-5 animate-spin" /> : label}
            </button>
          ))}
        </div>
        {/* On this card's own dark ground, not an ErrorBox: the buttons are
            still live, so saying what happened is the whole fix. */}
        {failed && (
          <p className="mt-3 flex items-start gap-2 text-[15px] text-white/90">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-ochre" />
            {t('notSaved')}
          </p>
        )}
      </div>
    </section>
  )
}

function Escalated({ message, kase, alternatives }: { message: string; kase?: CaseBrief; alternatives: TargetView[] }) {
  const { t } = useFarmer()
  return (
    <section className="space-y-6">
      <div className={`${PANEL} p-5 lg:p-6`}>
        <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-sky-100 text-sky-800">
          <UserRound className="h-7 w-7" aria-hidden />
        </span>
        <h1 className="mt-3 font-instrument-serif text-[30px] leading-tight">{t('sentToExpert')}</h1>
        <p className="mt-2 text-[15px] leading-relaxed text-soil-dark/85">{message}</p>
        <p className="mt-3 rounded-[18px] bg-[#fdf0ed] p-3.5 text-[15px] font-medium text-[#9a2f17]">{t('sentToExpertSub')}</p>
        {kase && kase.status === 'open' && (
          <div className="mt-4 grid grid-cols-2 gap-3">
            <div className="rounded-[20px] bg-[#f5f7f1] p-4">
              <p className="text-[13px] text-soil-dark/75">{t('queuePosition')}</p>
              <p className="mt-1 text-[26px] font-semibold tabular-nums">{kase.queue_position}</p>
            </div>
            <div className="rounded-[20px] bg-[#f5f7f1] p-4">
              <p className="text-[13px] text-soil-dark/75">{t('eta')}</p>
              <p className="mt-1 text-[26px] font-semibold tabular-nums">{kase.eta_minutes} <span className="text-[15px] font-normal">{t('minutes')}</span></p>
            </div>
          </div>
        )}
        <a href="tel:18001801551" className={`${SECONDARY} mt-4 w-full`}>
          <PhoneCall className="h-5 w-5" aria-hidden />
          {t('callKcc')}
        </a>
        {kase && <p className="mt-3 text-center text-[13px] text-soil-dark/60">{t('caseNumber').replace('{n}', String(kase.id))}</p>}
      </div>
      {alternatives.length > 0 && (
        <div className={`${PANEL} p-5`}>
          <Alternatives alts={alternatives} />
        </div>
      )}
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
    <section className="rounded-[28px] bg-[#fbf0dc] p-5 ring-1 ring-ochre/25 lg:p-6">
      <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#f6e2bb] text-[#8a5a17]">
        <ArrowRightLeft className="h-7 w-7" aria-hidden />
      </span>
      <h1 className="mt-3 font-instrument-serif text-[30px] leading-tight">{t('mismatchTitle').replace('{crop}', cropName)}</h1>
      <p className="mt-2 text-[15px] leading-relaxed text-soil-dark/85">
        {t('mismatchBody').replace('{name}', top.name).replace('{crop}', cropName)
          .replace('{pct}', String(Math.round((top.confidence ?? 0) * 100)))}
      </p>
      {others.length > 0 && (
        <>
          <p className="mt-4 text-[15px] font-semibold">{t('mismatchPick').replace('{crop}', cropName)}</p>
          <div className="mt-2 grid gap-2">
            {others.map((f) => (
              <button key={f.id} onClick={() => recheck(f)} disabled={busy !== null}
                className="flex min-h-[52px] items-center justify-between gap-2 rounded-2xl bg-white px-4 text-left text-[15px] ring-1 ring-soil-dark/10 disabled:opacity-60">
                <span><span className="font-semibold">{f.farmer_name}</span> <span className="text-[13px] text-soil-dark/70">· {f.district}</span></span>
                {busy === f.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <span className="text-[14px] font-semibold text-leaf-deep">{t('mismatchCheck')} →</span>}
              </button>
            ))}
          </div>
        </>
      )}
      {others.length === 0 && !adding && (
        <button onClick={() => setAdding(true)}
          className={`${PRIMARY} mt-4`}>
          <Plus className="w-4 h-4" />
          {t('mismatchAddField').replace('{crop}', cropName)}
        </button>
      )}
      {adding && (
        <div className="mt-4 space-y-4 rounded-[20px] bg-white p-4">
          <p className="text-[16px] font-semibold">{t('mismatchNewField').replace('{crop}', cropName)}</p>
          <label className={LABEL}>
            {t('sowingDate')}
            <input type="date" value={sowing} max={new Date().toISOString().slice(0, 10)}
              onChange={(e) => setSowing(e.target.value)}
              className={FIELD} />
          </label>
          <label className={LABEL}>
            {t('area')}
            <input type="number" inputMode="decimal" min="0.1" step="0.1" value={area}
              onChange={(e) => setArea(e.target.value)}
              className={FIELD} />
          </label>
          <button onClick={addAndCheck} disabled={busy !== null || !(parseFloat(area) > 0)}
            className={PRIMARY}>
            {busy !== null ? <Loader2 className="w-4 h-4 animate-spin" /> : <Camera className="w-4 h-4" />}
            {t('mismatchAddAndCheck')}
          </button>
        </div>
      )}
      {err && <p className="mt-3 text-[14px] text-ember">{err}</p>}
    </section>
  )
}
