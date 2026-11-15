import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowRight, Camera, CheckCircle2, CloudOff, Focus, Hand, ImagePlus, Loader2, ScanLine, Sun, Video, X,
} from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiError } from '../../api/client'
import type { ProblemView } from '../../api/types'
import { useAsync } from '../../lib/hooks'
import { shrink } from '../../lib/image'
import { EVENT, pendingPhotos, queuePhoto, type OutboxChange } from '../../lib/outbox'
import { ErrorBox } from '../../ui/kit'
import { useFarmer } from '../FarmerContext'
import DemoNotice, { useReadOnlyFarm } from '../components/DemoNotice'
import ProblemRow from '../components/ProblemRow'
import { PanelHead, hideBroken } from '../ui'
import { PANEL } from '../tokens'
import type { Lang } from '../../api/types'

/** The demo model's forced outcomes. Shown only while the trained model is not
 *  loaded, under the line saying so, but a farmer may still be the one holding
 *  the phone, so the chips speak their language. */
const SCENARIOS: { id: string; label: Record<Lang, string> }[] = [
  { id: '', label: { en: 'Auto', hi: 'स्वतः', mr: 'आपोआप', bn: 'স্বয়ংক্রিয়', ta: 'தானியங்கி', te: 'ఆటో', kn: 'ಸ್ವಯಂ', ml: 'ഓട്ടോ', gu: 'આપમેળે', pa: 'ਆਪਣੇ-ਆਪ' } },
  { id: 'clear', label: { en: 'Clear', hi: 'स्पष्ट', mr: 'स्पष्ट', bn: 'স্পষ্ট', ta: 'தெளிவு', te: 'స్పష్టం', kn: 'ಸ್ಪಷ್ಟ', ml: 'വ്യക്തം', gu: 'સ્પષ્ટ', pa: 'ਸਪਸ਼ਟ' } },
  { id: 'torn', label: { en: 'Torn', hi: 'दुविधा', mr: 'द्विधा', bn: 'দ্বিধা', ta: 'இரண்டில் ஒன்று', te: 'సందిగ్ధం', kn: 'ದ್ವಂದ್ವ', ml: 'ആശയക്കുഴപ്പം', gu: 'દ્વિધા', pa: 'ਦੁਬਿਧਾ' } },
  { id: 'unsure', label: { en: 'Unsure', hi: 'अनिश्चित', mr: 'अनिश्चित', bn: 'অনিশ্চিত', ta: 'உறுதியில்லை', te: 'అనిశ్చితం', kn: 'ಅನಿಶ್ಚಿತ', ml: 'ഉറപ്പില്ല', gu: 'અનિશ્ચિત', pa: 'ਅਨਿਸ਼ਚਿਤ' } },
]

// Dark text on ochre: cream on ochre is under 3:1 in sunlight.
const EXPECT_TINT = {
  clarify: 'bg-ochre text-soil-dark',
  escalate: 'bg-sky-700 text-white',
  retake: 'bg-soil-dark text-cream',
  advise: '',
} as const

export default function Scan() {
  const { farmId, lang, t, setResult } = useFarmer()
  const demoFarm = useReadOnlyFarm()
  const navigate = useNavigate()
  const cameraRef = useRef<HTMLInputElement>(null)
  const galleryRef = useRef<HTMLInputElement>(null)
  const [blob, setBlob] = useState<Blob | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [step, setStep] = useState(0)
  const [error, setError] = useState<Error | null>(null)
  const [saved, setSaved] = useState(false)
  const [waiting, setWaiting] = useState(0)
  const [scenario, setScenario] = useState('')
  const home = useAsync(() => api.home(farmId!, lang), [farmId, lang], ['home', farmId!, lang].join(':'))
  const farm = home.data?.farm
  const reloadHome = useRef(home.reload)
  useEffect(() => { reloadHome.current = home.reload })
  // Unknown until Home loads: never claim the demo model before we know.
  const isStub = home.data?.model.is_stub ?? false
  // Sample photos are scaffolding for showing the app without a sick plant at
  // hand. A real farmer's own field is the subject, so they never appear there.
  // The crop comes from the gate as well as from Home: on a shared field the
  // samples are the whole screen, and they must not wait on a second request.
  const sampleCrop = demoFarm?.crop ?? (farm?.is_demo ? farm.crop : null)
  const samples = useAsync(() => (sampleCrop ? api.samples(sampleCrop) : Promise.resolve([])),
    [sampleCrop])
  // A handful, one per problem, not the whole scoring set.
  const shown = useMemo(() => {
    const seen = new Set<string>()
    return (samples.data ?? []).filter((x) => !seen.has(x.true_class) && seen.add(x.true_class)).slice(0, 8)
  }, [samples.data])
  const steps = t('scanningSteps').split('|')

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview)
  }, [preview])

  useEffect(() => {
    if (!busy) return
    const id = setInterval(() => setStep((s) => Math.min(s + 1, steps.length - 1)), 650)
    return () => clearInterval(id)
  }, [busy, steps.length])

  // Photos from this field still waiting for signal, kept current as the
  // outbox sends them (the shell sends; this only counts).
  useEffect(() => {
    if (farmId == null) return
    let on = true
    const count = () => void pendingPhotos(farmId).then((p) => { if (on) setWaiting(p.length) }).catch(() => undefined)
    count()
    const changed = (e: Event) => {
      count()
      if ((e as CustomEvent<OutboxChange>).detail?.sent?.farmId === farmId) {
        setSaved(false)
        reloadHome.current()   // the answer joins "Your earlier photos"
      }
    }
    window.addEventListener(EVENT, changed)
    return () => {
      on = false
      window.removeEventListener(EVENT, changed)
    }
  }, [farmId])

  const pick = async (f: Blob) => {
    setError(null)
    setSaved(false)
    const small = await shrink(f)
    setBlob(small)
    setPreview(URL.createObjectURL(small))
  }
  const clear = () => {
    setBlob(null)
    setPreview(null)
  }

  const run = async () => {
    if (!blob) return
    setStep(0)
    setBusy(true)
    setError(null)
    try {
      const [r] = await Promise.all([
        api.diagnose(farmId!, blob, lang, isStub ? scenario || undefined : undefined),
        new Promise((res) => setTimeout(res, 1900)), // let the farmer see what is being checked
      ])
      setResult(r)
      navigate('/app/result')
    } catch (e) {
      // No signal at the edge of the field: keep the photo on the phone and
      // send it when there is, rather than losing what they walked out to take.
      if (e instanceof ApiError && e.status === 0 && !isStub) {
        try {
          await queuePhoto(farmId!, blob, lang)
          clear()
          setSaved(true)
          setBusy(false)
          return
        } catch { /* storage refused: fall through to the error */ }
      }
      setError(e as Error)
      setBusy(false)
    }
  }

  const inputs = (
    <>
      <input ref={cameraRef} type="file" accept="image/*" capture="environment" className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) void pick(f)
          e.target.value = ''
        }} />
      <input ref={galleryRef} type="file" accept="image/*" className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) void pick(f)
          e.target.value = ''
        }} />
    </>
  )

  const samplesEl = !busy && (demoFarm ? true : !preview) && shown.length > 0 && (
    <section className={`${PANEL} p-5`}>
      <PanelHead title={t('samplesTitle')} />
      {/* Three across on a phone: at four, a 12px label has ~60px and "white
          stem borer" could only be clipped. */}
      <div className="mt-4 grid grid-cols-3 gap-2.5 sm:grid-cols-4 lg:grid-cols-3">
        {shown.map((s) => {
          const Frame = demoFarm ? 'span' : 'button'
          return (
            <Frame key={s.url}
              {...(demoFarm ? {} : { onClick: async () => pick(await (await fetch(s.url)).blob()) })}
              className="block text-left">
              <span className="relative block">
                <img src={s.url} alt={s.true_class} loading="lazy" className="aspect-square w-full rounded-2xl object-cover ring-1 ring-soil-dark/10" />
                {s.expected && s.expected !== 'advise' && (
                  <span className={`absolute inset-x-1 bottom-1 rounded-md px-1 py-0.5 text-center text-[12px] font-semibold leading-tight ${EXPECT_TINT[s.expected]}`}>
                    {t(`expect_${s.expected}`)}
                  </span>
                )}
              </span>
              <span className="mt-1 block text-[13px] leading-snug text-soil-dark/80 [overflow-wrap:anywhere]">
                {s.true_class.replace(/^(rice|maize|cotton|soybean)_/, '').replace(/_/g, ' ')}
              </span>
            </Frame>
          )
        })}
      </div>
    </section>
  )

  // A shared demo field cannot take a photo: the samples are the screen.
  if (demoFarm) {
    return (
      <div className="space-y-6">
        <DemoNotice title={t('demoScanTitle')} body={t('demoScanBody')} />
        {samplesEl}
      </div>
    )
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px] xl:grid-cols-[minmax(0,1fr)_420px]">
      <div className="min-w-0 space-y-6">
        {farm && !farm.photo_diagnosis && (
          <p className="rounded-[20px] bg-sky-50 p-4 text-[15px] text-sky-950/85">{t('photoLater')}</p>
        )}
        {saved && (
          <div role="status" className="flex items-start gap-3 rounded-[20px] bg-[#fbf0dc] p-4">
            <CloudOff className="mt-0.5 h-6 w-6 shrink-0 text-[#8a5a17]" aria-hidden />
            <div>
              <p className="text-[16px] font-semibold text-[#7a4f12]">{t('scanSavedTitle')}</p>
              <p className="mt-0.5 text-[15px] text-soil-dark/80">{t('scanSavedBody')}</p>
            </div>
          </div>
        )}
        <section className={`${PANEL} p-2`}>
          <div className="relative aspect-[4/5] overflow-hidden rounded-[22px] bg-leaf-deep sm:aspect-[16/11]">
            {preview ? (
              <>
                <img src={preview} alt="" className="absolute inset-0 h-full w-full object-cover" />
                {busy && (
                  <>
                    <div className="absolute inset-0 bg-leaf-deep/35" />
                    <div className="absolute inset-x-0 h-24 bg-gradient-to-b from-transparent via-ochre/60 to-transparent motion-safe:animate-[scan_1.6s_ease-in-out_infinite]" />
                  </>
                )}
                {!busy && (
                  <button onClick={clear} aria-label={t('scanRemove')}
                    className="absolute right-3 top-3 flex h-11 w-11 items-center justify-center rounded-full bg-black/55 text-white">
                    <X className="h-5 w-5" />
                  </button>
                )}
              </>
            ) : (
              <>
                {/* A leaf held up to the light: what the photo should look like. */}
                <img onError={hideBroken} src="/photos/leaf-dew.webp" alt="" width={950} height={442}
                  className="absolute inset-0 h-full w-full object-cover" />
                <div aria-hidden className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/30 to-black/10" />
                <button onClick={() => cameraRef.current?.click()}
                  className="absolute inset-0 flex flex-col items-center justify-center gap-4 px-6 text-center text-white">
                  <span className="flex h-24 w-24 items-center justify-center rounded-full bg-white/95 text-[#2f6a39] shadow-[0_12px_30px_-10px_rgba(0,0,0,0.6)] ring-8 ring-white/25">
                    <Camera className="h-11 w-11" strokeWidth={1.8} aria-hidden />
                  </span>
                  <span>
                    <span className="block font-instrument-serif text-[32px] leading-tight drop-shadow sm:text-[38px]">{t('takePhoto')}</span>
                    <span className="mt-1 block text-[15px] text-white/90 drop-shadow">{t('takePhotoSub')}</span>
                  </span>
                </button>
              </>
            )}
            {/* The corners of a viewfinder, so the leaf is put in the middle. */}
            <span aria-hidden className="pointer-events-none absolute inset-5">
              <span className="absolute left-0 top-0 h-8 w-8 rounded-tl-2xl border-l-[3px] border-t-[3px] border-white/80" />
              <span className="absolute right-0 top-0 h-8 w-8 rounded-tr-2xl border-r-[3px] border-t-[3px] border-white/80" />
              <span className="absolute bottom-0 left-0 h-8 w-8 rounded-bl-2xl border-b-[3px] border-l-[3px] border-white/80" />
              <span className="absolute bottom-0 right-0 h-8 w-8 rounded-br-2xl border-b-[3px] border-r-[3px] border-white/80" />
            </span>
          </div>
          {inputs}
          <div className="p-3 sm:p-4">
            {busy ? (
              <ol className="space-y-2.5 rounded-[20px] bg-[#f5f7f1] p-4" aria-live="polite">
                {steps.map((s, i) => (
                  <li key={s} className={`flex items-center gap-2.5 text-[15px] transition-opacity ${i <= step ? 'opacity-100' : 'opacity-40'}`}>
                    {i < step ? <CheckCircle2 className="h-5 w-5 text-[#4b8b3b]" />
                      : i === step ? <Loader2 className="h-5 w-5 animate-spin text-ochre" /> : <ScanLine className="h-5 w-5" />}
                    {s}
                  </li>
                ))}
              </ol>
            ) : preview ? (
              <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
                <button onClick={run}
                  className="flex min-h-[56px] items-center justify-center gap-2 rounded-full bg-[#2f6a39] text-[17px] font-semibold text-white shadow-[0_12px_24px_-14px_rgba(29,74,44,0.8)] transition-colors hover:bg-[#2a5f33]">
                  <ScanLine className="h-5 w-5" aria-hidden /> {t('scanCheck')}
                </button>
                <button onClick={() => cameraRef.current?.click()}
                  className="flex min-h-[56px] items-center justify-center gap-2 rounded-full bg-[#eef3e6] px-6 text-[15px] font-semibold text-leaf-deep ring-1 ring-[#4b8b3b]/15 hover:bg-[#e6eedb]">
                  <Camera className="h-5 w-5" aria-hidden /> {t('scanRetake')}
                </button>
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                <button onClick={() => cameraRef.current?.click()}
                  className="flex min-h-[56px] items-center justify-center gap-2 rounded-full bg-[#2f6a39] text-[17px] font-semibold text-white shadow-[0_12px_24px_-14px_rgba(29,74,44,0.8)] transition-colors hover:bg-[#2a5f33]">
                  <Camera className="h-5 w-5" aria-hidden /> {t('scanOpenCamera')}
                </button>
                <button onClick={() => galleryRef.current?.click()}
                  className="flex min-h-[56px] items-center justify-center gap-2 rounded-full bg-[#eef3e6] text-[15px] font-semibold text-leaf-deep ring-1 ring-[#4b8b3b]/15 hover:bg-[#e6eedb]">
                  <ImagePlus className="h-5 w-5" aria-hidden /> {t('scanGallery')}
                </button>
              </div>
            )}
            {error && <div className="mt-3"><ErrorBox offlineLabel={t('offline')} error={error} /></div>}
            {waiting > 0 && !saved && (
              <p role="status" className="mt-3 flex items-center gap-2 text-[14px] text-[#7a4f12]">
                <CloudOff className="h-4 w-4 shrink-0" aria-hidden />
                {t('scanWaiting').replace('{n}', String(waiting))}
              </p>
            )}
          </div>
        </section>
        {!busy && isStub && (
          <div className="rounded-[20px] border border-dashed border-ochre/50 p-4">
            <p id="scan-demo-model" className="text-[13px] text-[#8a5a17]">{t('demoModel')}</p>
            <div role="group" aria-labelledby="scan-demo-model" className="mt-2 flex flex-wrap gap-1.5">
              {SCENARIOS.map((s) => (
                <button key={s.id} type="button" onClick={() => setScenario(s.id)} aria-pressed={scenario === s.id}
                  className={`min-h-[44px] rounded-full px-4 text-[13px] font-medium ${scenario === s.id ? 'bg-ochre text-soil-dark' : 'bg-white ring-1 ring-soil-dark/15'}`}>
                  {s.label[lang]}
                </button>
              ))}
            </div>
          </div>
        )}
        <Tips />
      </div>
      <aside className="min-w-0 space-y-6">
        <LivePanel />
        <RecentScans problems={home.data?.problems ?? []} />
        {samplesEl}
      </aside>
    </div>
  )
}

/** Three things that decide whether a photo can be read at all. */
function Tips() {
  const { t } = useFarmer()
  const tips = [
    [Focus, t('scanTip1')],
    [Sun, t('scanTip2')],
    [Hand, t('scanTip3')],
  ] as const
  return (
    <section className={`${PANEL} p-5 lg:p-6`}>
      <h2 className="text-[20px] font-semibold tracking-tight sm:text-[22px]">{t('scanTipsTitle')}</h2>
      <ul className="mt-4 grid gap-3 sm:grid-cols-3">
        {tips.map(([Icon, text]) => (
          <li key={text} className="flex items-center gap-3 rounded-[20px] bg-[#f5f7f1] p-3.5 sm:flex-col sm:items-start">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-[#e3efd9] text-[#2f6a39]">
              <Icon className="h-6 w-6" aria-hidden />
            </span>
            <span className="text-[15px] leading-snug">{text}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** The other way to ask: show the field on a video call. */
function LivePanel() {
  const { t } = useFarmer()
  return (
    <Link to="/app/live"
      className="group relative block overflow-hidden rounded-[28px] bg-[#1d4a2c] text-white shadow-[0_14px_30px_-16px_rgba(29,74,44,0.8)]">
      <img onError={hideBroken} src="/photos/panicle-closeup.webp" alt="" width={940} height={442} loading="lazy"
        className="absolute inset-0 h-full w-full object-cover opacity-45" />
      <div aria-hidden className="absolute inset-0 bg-gradient-to-t from-[#1d4a2c] via-[#1d4a2c]/80 to-[#1d4a2c]/30" />
      <div className="relative p-5">
        <div className="flex items-start justify-between">
          <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/15">
            <Video className="h-7 w-7" aria-hidden />
          </span>
          <span className="rounded-full bg-ember px-2.5 py-0.5 text-[12px] font-bold tracking-wide">LIVE</span>
        </div>
        <h2 className="mt-8 text-[22px] font-semibold leading-tight">{t('liveCta')}</h2>
        <p className="mt-1.5 text-[15px] leading-snug text-white/85">{t('liveCtaSub')}</p>
        <span className="mt-4 inline-flex min-h-[48px] items-center gap-2 rounded-full bg-white px-5 text-[15px] font-semibold text-[#1d4a2c] transition-transform group-hover:translate-x-0.5">
          {t('scanStartLive')} <ArrowRight className="h-4 w-4" aria-hidden />
        </span>
      </div>
    </Link>
  )
}

/** What this field's earlier photos found, so a farmer can see an answer is
 *  already waiting before taking another. */
function RecentScans({ problems }: { problems: ProblemView[] }) {
  const { t } = useFarmer()
  const recent = problems.filter((p) => p.gate_outcome !== 'retake').slice(0, 3)
  if (recent.length === 0) return null
  return (
    <section className={`${PANEL} p-5`}>
      <PanelHead title={t('scanRecent')}
        action={(
          <Link to="/app/history" className="-my-2 flex min-h-[44px] shrink-0 items-center gap-1 whitespace-nowrap text-[15px] font-medium text-leaf-deep hover:underline">
            {t('seeAll')} <ArrowRight className="h-4 w-4" aria-hidden />
          </Link>
        )} />
      <ul className="mt-3 space-y-2">
        {recent.map((p) => <li key={p.id}><ProblemRow p={p} size="sm" /></li>)}
      </ul>
    </section>
  )
}
