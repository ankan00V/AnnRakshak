import { useEffect, useRef, useState } from 'react'
import { Camera, CheckCircle2, ImagePlus, Loader2, ScanLine, Video, X } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import { useAsync } from '../../lib/hooks'
import { ErrorBox, Pill } from '../../ui/kit'
import { useFarmer } from '../FarmerContext'

/** Downscale on the phone before upload: field networks are slow and the model
 *  only needs ~300 px anyway. */
async function shrink(file: Blob, max = 1280): Promise<Blob> {
  const bmp = await createImageBitmap(file)
  const scale = Math.min(1, max / Math.max(bmp.width, bmp.height))
  const c = document.createElement('canvas')
  c.width = Math.round(bmp.width * scale)
  c.height = Math.round(bmp.height * scale)
  c.getContext('2d')!.drawImage(bmp, 0, 0, c.width, c.height)
  return new Promise((res) => c.toBlob((b) => res(b ?? file), 'image/jpeg', 0.88))
}

const SCENARIOS = [
  { id: '', label: 'Auto' },
  { id: 'clear', label: 'Clear' },
  { id: 'torn', label: 'Torn' },
  { id: 'unsure', label: 'Unsure' },
]

const EXPECT_TINT = {
  clarify: 'bg-ochre text-cream',
  escalate: 'bg-sky-700 text-white',
  retake: 'bg-soil-dark text-cream',
  advise: '',
} as const

export default function Scan() {
  const { farmId, lang, t, setResult } = useFarmer()
  const navigate = useNavigate()
  const fileRef = useRef<HTMLInputElement>(null)
  const [blob, setBlob] = useState<Blob | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [step, setStep] = useState(0)
  const [error, setError] = useState<Error | null>(null)
  const [scenario, setScenario] = useState('')
  const home = useAsync(() => api.home(farmId!, lang), [farmId, lang], ['home', farmId!, lang].join(':'))
  const farm = home.data?.farm
  const isStub = home.data?.model.is_stub ?? true
  // Sample photos are scaffolding for showing the app without a sick plant at
  // hand. A real farmer's own field is the subject, so they never appear there.
  const samples = useAsync(() => (farm?.is_demo ? api.samples(farm.crop) : Promise.resolve([])),
    [farm?.crop, farm?.is_demo])
  const steps = t('scanningSteps').split('|')

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview)
  }, [preview])

  useEffect(() => {
    if (!busy) return
    const id = setInterval(() => setStep((s) => Math.min(s + 1, steps.length - 1)), 650)
    return () => clearInterval(id)
  }, [busy, steps.length])

  const pick = async (f: Blob) => {
    setError(null)
    const small = await shrink(f)
    setBlob(small)
    setPreview(URL.createObjectURL(small))
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
      setError(e as Error)
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="font-instrument-serif text-3xl leading-tight">{t('takePhoto')}</h1>

      <Link to="/app/live" className="flex items-center gap-3 rounded-2xl border border-leaf/30 bg-white p-3 text-sm">
        <span className="shrink-0 w-9 h-9 rounded-full bg-ember/10 text-ember flex items-center justify-center"><Video className="w-4 h-4" /></span>
        <span className="flex-1"><span className="font-medium">{t('liveCta')}</span><span className="block text-xs text-soil-dark/60">{t('liveTitle')}</span></span>
        <span className="text-leaf-deep">→</span>
      </Link>

      {farm && !farm.photo_diagnosis && (
        <p className="text-sm rounded-2xl bg-sky-50 text-sky-900 p-3">{t('photoLater')}</p>
      )}

      <div className="relative aspect-square w-full rounded-3xl overflow-hidden bg-soil-dark">
        {preview ? (
          <>
            <img src={preview} alt="" className="w-full h-full object-cover" />
            {busy && (
              <>
                <div className="absolute inset-0 bg-leaf-deep/40" />
                <div className="absolute inset-x-0 h-24 bg-gradient-to-b from-transparent via-ochre/60 to-transparent animate-[scan_1.6s_ease-in-out_infinite]" />
              </>
            )}
            {!busy && (
              <button
                onClick={() => {
                  setBlob(null)
                  setPreview(null)
                }}
                aria-label="Remove photo"
                className="absolute top-3 right-3 w-9 h-9 rounded-full bg-black/50 text-white flex items-center justify-center"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </>
        ) : (
          <button onClick={() => fileRef.current?.click()} className="w-full h-full flex flex-col items-center justify-center gap-3 text-cream">
            <span className="relative w-24 h-24 rounded-full border-2 border-dashed border-ochre/60 flex items-center justify-center">
              <Camera className="w-10 h-10 text-ochre" />
            </span>
            <span className="text-base font-medium">{t('takePhoto')}</span>
            <span className="text-xs text-cream/60 max-w-[240px] text-center">{t('retakeTips')}</span>
          </button>
        )}
        <span aria-hidden className="pointer-events-none absolute inset-6 border-2 border-cream/20 rounded-2xl" />
      </div>
      <input ref={fileRef} type="file" accept="image/*" capture="environment" className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) pick(f)
          e.target.value = ''
        }} />

      {busy ? (
        <ol className="rounded-2xl bg-white border border-soil-dark/10 p-4 space-y-2">
          {steps.map((s, i) => (
            <li key={s} className={`flex items-center gap-2 text-sm transition-opacity ${i <= step ? 'opacity-100' : 'opacity-30'}`}>
              {i < step ? <CheckCircle2 className="w-4 h-4 text-leaf" /> : i === step ? <Loader2 className="w-4 h-4 animate-spin text-ochre" /> : <ScanLine className="w-4 h-4" />}
              {s}
            </li>
          ))}
        </ol>
      ) : preview ? (
        <button onClick={run} className="w-full min-h-[56px] rounded-full bg-leaf-deep text-cream text-base font-medium flex items-center justify-center gap-2 shadow-lg shadow-leaf-deep/20">
          <ScanLine className="w-5 h-5" />
          {t('scan')}
        </button>
      ) : (
        <button onClick={() => fileRef.current?.click()} className="w-full min-h-[52px] rounded-full border border-soil-dark/20 text-sm font-medium flex items-center justify-center gap-2 bg-white">
          <ImagePlus className="w-4 h-4" />
          {t('takePhoto')}
        </button>
      )}

      {error && <ErrorBox error={error} />}

      {!busy && isStub && (
        <div className="rounded-2xl border border-dashed border-ochre/50 p-3">
          <p className="text-[11px] text-[#8a5a17]">{t('demoModel')}</p>
          <div className="mt-2 flex gap-1.5 flex-wrap">
            {SCENARIOS.map((s) => (
              <button key={s.id} onClick={() => setScenario(s.id)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium ${scenario === s.id ? 'bg-ochre text-cream' : 'bg-white border border-soil-dark/15'}`}>
                {s.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {!busy && !preview && samples.data && samples.data.length > 0 && (
        <div>
          <p className="text-xs text-soil-dark/50 mb-2">{t('samplesTitle')}</p>
          <div className="flex gap-2 overflow-x-auto no-scrollbar pb-1">
            {samples.data.map((s) => (
              <button key={s.url} onClick={async () => pick(await (await fetch(s.url)).blob())}
                className="shrink-0 w-20 text-left">
                <span className="relative block">
                  <img src={s.url} alt={s.true_class} className="w-20 h-20 rounded-xl object-cover border border-soil-dark/10" loading="lazy" />
                  {s.expected && s.expected !== 'advise' && (
                    <span className={`absolute bottom-1 inset-x-1 rounded-md px-1 py-0.5 text-[8.5px] leading-tight font-semibold text-center ${EXPECT_TINT[s.expected]}`}>
                      {t(`expect_${s.expected}`)}
                    </span>
                  )}
                </span>
                <Pill className="mt-1 !text-[9px] !px-1.5">{s.true_class.replace(/^(rice|maize)_/, '').replace(/_/g, ' ')}</Pill>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
