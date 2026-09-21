import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AlertTriangle, CameraOff, CheckCircle2, CloudSun, Droplets, Eye, Leaf, Loader2, MapPin, ScanSearch, ShieldAlert,
  Sprout, Stethoscope, Video, Volume2, VolumeX, X,
} from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import type { LiveContext, LiveFrameReply, LiveGuide, LiveSummary, TargetView } from '../../api/types'
import { useAsync } from '../../lib/hooks'
import { Speaker } from '../../lib/speaker'
import { Card, ErrorBox, ListenButton, Pill } from '../../ui/kit'
import { useFarmer } from '../FarmerContext'

type Phase = 'intro' | 'starting' | 'live' | 'finishing' | 'summary' | 'error'
type Ask = { cue_id: string; question: string; candidates: TargetView[] }

const FRAME_EVERY_MS = 650   // ~1.5 frames/s, each ~20-40 KB: works on a 3G/4G link
const FRAME_MAX_SIDE = 512
const INFLIGHT_TIMEOUT_MS = 6000
const FINISH_TIMEOUT_MS = 25000
const MIN_FRAME_SIDE = 64        // a stopped or starting track gives 0-2 px frames

function position(timeoutMs = 6000): Promise<GeolocationPosition | null> {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve(null)
    const t = setTimeout(() => resolve(null), timeoutMs)
    navigator.geolocation.getCurrentPosition(
      (p) => { clearTimeout(t); resolve(p) },
      () => { clearTimeout(t); resolve(null) },
      { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 60000 },
    )
  })
}

export default function Live() {
  const { farmId, lang, t } = useFarmer()
  const navigate = useNavigate()
  const home = useAsync(() => api.home(farmId!, lang), [farmId, lang], ['home', farmId!, lang].join(':'))
  const [phase, setPhase] = useState<Phase>('intro')
  const [error, setError] = useState<string | null>(null)
  const [ctx, setCtx] = useState<LiveContext | null>(null)
  const [guide, setGuide] = useState<LiveGuide | null>(null)
  const [quality, setQuality] = useState<LiveFrameReply['quality']>(null)
  const [flash, setFlash] = useState(0)
  const [liveTop, setLiveTop] = useState<{ name: string; confidence: number; healthy: boolean } | null>(null)
  const [tally, setTally] = useState<Record<string, { name: string; n: number }>>({})
  const [ask, setAsk] = useState<Ask | null>(null)
  const [expertChoice, setExpertChoice] = useState(false)
  const [summary, setSummary] = useState<LiveSummary | null>(null)
  const [muted, setMuted] = useState(false)

  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const speakerRef = useRef<Speaker | null>(null)
  const loopRef = useRef<number | null>(null)
  const fresh = () => ({ seq: 0, inflight: false, sentAt: 0, capturing: false, photoModel: true, finishing: false, done: false })
  const st = useRef(fresh())
  const finishTimer = useRef<number | null>(null)

  const stopCamera = useCallback(() => {
    if (loopRef.current) window.clearInterval(loopRef.current)
    loopRef.current = null
    st.current.capturing = false
    streamRef.current?.getTracks().forEach((tr) => tr.stop())
    streamRef.current = null
  }, [])

  useEffect(() => () => {
    stopCamera()
    if (finishTimer.current) window.clearTimeout(finishTimer.current)
    if (wsRef.current) {
      wsRef.current.onclose = null
      wsRef.current.close()
    }
    speakerRef.current?.dispose()
  }, [stopCamera])

  /** The call dropped (network, server restart) before the summary arrived. */
  const lost = useCallback(() => {
    if (st.current.done) return
    st.current.done = true
    if (finishTimer.current) window.clearTimeout(finishTimer.current)
    stopCamera()
    speakerRef.current?.stop()
    setAsk(null)
    setExpertChoice(false)
    setError(t('liveLost'))
    setPhase('error')
  }, [stopCamera, t])

  const finish = useCallback((sendToExpert: boolean) => {
    if (st.current.finishing) return
    st.current.finishing = true
    st.current.capturing = false
    setPhase('finishing')
    speakerRef.current?.stop()
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return lost()
    ws.send(JSON.stringify({ type: 'finish', send_to_expert: sendToExpert }))
    finishTimer.current = window.setTimeout(lost, FINISH_TIMEOUT_MS)
  }, [lost])

  const sendFrame = useCallback(() => {
    const s = st.current
    const ws = wsRef.current
    const v = videoRef.current
    const c = canvasRef.current
    if (!s.capturing || !ws || ws.readyState !== WebSocket.OPEN || !v || !c || v.readyState < 2) return
    if (Math.min(v.videoWidth, v.videoHeight) < MIN_FRAME_SIDE) return
    const now = Date.now()
    if (s.inflight && now - s.sentAt < INFLIGHT_TIMEOUT_MS) return
    if (now - s.sentAt < FRAME_EVERY_MS) return
    const scale = Math.min(1, FRAME_MAX_SIDE / Math.max(v.videoWidth, v.videoHeight))
    c.width = Math.round(v.videoWidth * scale)
    c.height = Math.round(v.videoHeight * scale)
    c.getContext('2d')!.drawImage(v, 0, 0, c.width, c.height)
    const data = c.toDataURL('image/jpeg', 0.72).split(',')[1]
    s.seq += 1
    s.inflight = true
    s.sentAt = now
    ws.send(JSON.stringify({ type: 'frame', seq: s.seq, data }))
  }, [])

  const onMessage = useCallback((ev: MessageEvent) => {
    const m = JSON.parse(ev.data)
    const sp = speakerRef.current
    if (m.type === 'ready') {
      setCtx(m.context)
      setGuide(m.guide)
      st.current.photoModel = m.photo_model
      setPhase('live')
      st.current.capturing = true
      void sp?.prompt(m.guide.text)
    } else if (m.type === 'frame') {
      const r = m as LiveFrameReply
      st.current.inflight = false
      setQuality(r.quality)
      if (r.counted) setFlash((f) => f + 1)
      if (r.live?.top?.length) {
        const top = r.live.top[0]
        const healthy = top.target.endsWith('_healthy')
        setLiveTop({ name: top.name, confidence: top.confidence, healthy })
        if (!healthy && top.confidence >= 0.4) {
          setTally((prev) => ({ ...prev, [top.target]: { name: top.name, n: (prev[top.target]?.n ?? 0) + 1 } }))
        }
      }
      setGuide(r.guide)
      if (r.advanced && r.guide.text) void sp?.prompt(r.guide.text)
      else if (r.quality && !r.quality.ok && r.quality.hint_text) void sp?.hint(r.quality.hint_text)
    } else if (m.type === 'ask') {
      st.current.capturing = false
      setAsk(m)
      void sp?.prompt(m.question)
    } else if (m.type === 'steps_done') {
      st.current.capturing = false
      if (m.asked) return
      if (st.current.photoModel) finish(false)
      else setExpertChoice(true)
    } else if (m.type === 'summary') {
      st.current.done = true
      if (finishTimer.current) window.clearTimeout(finishTimer.current)
      stopCamera()
      setSummary(m.summary)
      setPhase('summary')
      void sp?.prompt(m.summary.speech)
    } else if (m.type === 'lang') {
      // Language switched mid-call: the server re-sent the context and the current step.
      setCtx(m.context)
      setGuide(m.guide)
      void sp?.prompt(m.guide.text)
    } else if (m.type === 'error') {
      st.current.inflight = false
      if (m.code === 'SESSION_LIMIT') finish(false)
    }
  }, [finish, stopCamera])

  // A language change takes effect at once: mid-call the server switches the
  // guidance and context; after the call the summary is re-rendered from what was saved.
  const langSeen = useRef(lang)
  useEffect(() => {
    if (langSeen.current === lang) return
    langSeen.current = lang
    speakerRef.current?.setLang(lang)
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'lang', lang }))
    if (summary && farmId != null) {
      api.liveSummary(farmId, summary.scan_id, lang).then(setSummary).catch(() => undefined)
    }
  }, [lang, summary, farmId])

  const start = async () => {
    setPhase('starting')
    setError(null)
    st.current = fresh()
    setTally({})
    setAsk(null)
    setExpertChoice(false)
    speakerRef.current?.dispose()
    speakerRef.current = new Speaker(lang)
    speakerRef.current.muted = muted
    const where = position()
    try {
      streamRef.current = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      })
    } catch {
      setError(t('liveNoCamera'))
      setPhase('error')
      return
    }
    // another app taking the camera, or the OS revoking it, ends the track without an error
    streamRef.current.getVideoTracks()[0]?.addEventListener('ended', () => {
      if (st.current.finishing) return
      stopCamera()
      wsRef.current?.close()
      setError(t('liveNoCamera'))
      setPhase('error')
    })
    const v = videoRef.current!
    v.srcObject = streamRef.current
    await v.play().catch(() => undefined)
    const pos = await where
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/api/live/${farmId}`)
    wsRef.current = ws
    ws.onopen = () => ws.send(JSON.stringify({
      type: 'start', lang,
      lat: pos?.coords.latitude ?? null, lon: pos?.coords.longitude ?? null, accuracy: pos?.coords.accuracy ?? null,
    }))
    ws.onmessage = onMessage
    ws.onclose = lost  // also fires after onerror
    loopRef.current = window.setInterval(sendFrame, 150)
  }

  const answer = (a: 'yes' | 'no' | 'unknown') => {
    if (!ask) return
    wsRef.current?.send(JSON.stringify({ type: 'answer', cue_id: ask.cue_id, answer: a }))
    setAsk(null)
    finish(false)
  }

  const toggleMute = () => {
    const next = !muted
    setMuted(next)
    if (speakerRef.current) {
      speakerRef.current.muted = next
      if (next) speakerRef.current.stop()
    }
  }

  const farm = home.data?.farm
  const live = phase === 'starting' || phase === 'live' || phase === 'finishing'

  if (phase === 'summary' && summary) {
    return <SummaryView s={summary} onAgain={() => { setSummary(null); setPhase('intro') }} onDone={() => navigate('/app')} />
  }

  return (
    <div className="space-y-4">
      {!live && (
        <>
          <div className="pt-1">
            <p className="inline-flex items-center gap-1.5 rounded-full bg-ember/10 text-ember text-[11px] font-semibold px-2.5 py-1">
              <span className="w-1.5 h-1.5 rounded-full bg-ember animate-pulse" /> LIVE
            </p>
            <h1 className="mt-2 font-instrument-serif text-3xl leading-tight">{t('liveTitle')}</h1>
            <p className="mt-1 text-sm text-soil-dark/60">{t('liveCtaSub')}</p>
          </div>
          <Card className="p-4 space-y-3">
            {[[Video, t('liveHow1')], [Eye, t('liveHow2')], [ShieldAlert, t('liveHow3')]].map(([Icon, text], i) => {
              const I = Icon as typeof Video
              return (
                <p key={i} className="flex gap-3 text-sm">
                  <span className="shrink-0 w-8 h-8 rounded-full bg-leaf/10 text-leaf-deep flex items-center justify-center"><I className="w-4 h-4" /></span>
                  <span className="pt-1">{text as string}</span>
                </p>
              )
            })}
          </Card>
          {farm && !farm.photo_diagnosis && (
            <p className="text-sm rounded-2xl bg-sky-50 text-sky-900 p-3">{t('liveNoModel')}</p>
          )}
          {phase === 'error' && error && (
            <ErrorBox error={new Error(error)} />
          )}
          <button onClick={start}
            className="w-full min-h-[56px] rounded-full bg-leaf-deep text-cream text-base font-medium flex items-center justify-center gap-2 shadow-lg shadow-leaf-deep/25">
            <Video className="w-5 h-5" /> {t('liveStart')}
          </button>
        </>
      )}

      {/* The call: full screen over the app chrome while it runs. */}
      <div className={live ? 'fixed inset-0 z-[60] bg-black text-white' : 'hidden'}>
        <video ref={videoRef} playsInline muted className="absolute inset-0 w-full h-full object-cover" />
        <canvas ref={canvasRef} className="hidden" />

        <div className="absolute inset-x-0 top-0 p-4 pt-[max(1rem,env(safe-area-inset-top))] bg-gradient-to-b from-black/80 via-black/50 to-transparent">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-ember px-2 py-0.5 text-[11px] font-bold">
              <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" /> LIVE
            </span>
            {guide && guide.total > 0 && (
              <div className="flex-1 flex gap-1">
                {Array.from({ length: guide.total }).map((_, i) => (
                  <span key={i} className={`h-1 flex-1 rounded-full ${i < guide.index ? 'bg-leaf' : i === guide.index ? 'bg-ochre' : 'bg-white/25'}`} />
                ))}
              </div>
            )}
            <button onClick={toggleMute} aria-label={muted ? t('liveUnmute') : t('liveMute')}
              className="w-9 h-9 rounded-full bg-white/15 flex items-center justify-center">
              {muted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
            </button>
          </div>
          {guide?.step && (
            <>
              <p className="mt-3 text-[11px] uppercase tracking-wide text-white/60">
                {t('liveStep').replace('{i}', String(guide.index + 1)).replace('{n}', String(guide.total))}
              </p>
              <p className="mt-0.5 text-lg font-semibold leading-snug">{guide.text}</p>
              {guide.need ? (
                <div className="mt-2 flex gap-1.5">
                  {Array.from({ length: guide.need }).map((_, i) => (
                    <span key={i} className={`w-2.5 h-2.5 rounded-full ${i < (guide.got ?? 0) ? 'bg-leaf' : 'bg-white/30'}`} />
                  ))}
                </div>
              ) : null}
            </>
          )}
          <div className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
            {ctx?.weather_now?.temp_c != null && (
              <span className="inline-flex items-center gap-1 rounded-full bg-white/15 px-2 py-0.5">
                <CloudSun className="w-3 h-3" /> {Math.round(ctx.weather_now.temp_c)}° · {ctx.weather_now.rh_pct}%
              </span>
            )}
            {ctx && (
              <span className="inline-flex items-center gap-1 rounded-full bg-white/15 px-2 py-0.5">
                <MapPin className="w-3 h-3" />
                {ctx.location.source === 'gps'
                  ? t('liveGps').replace('{m}', String(Math.round(ctx.location.accuracy_m ?? 0)))
                  : t('liveFarmLoc')}
              </span>
            )}
          </div>
        </div>

        {/* Where to aim: a leaf-sized box for close-ups, the whole frame otherwise. */}
        {phase === 'live' && guide?.step && (
          <div key={flash} className={`absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 border-2 rounded-3xl transition-colors ${
            guide.kind === 'close' ? 'w-[62vw] h-[62vw] max-w-sm max-h-96' : 'w-[88vw] h-[46vh]'
          } ${flash ? 'animate-[pulse_0.6s_ease-out_1] border-leaf' : 'border-white/50'}`} />
        )}

        <div className="absolute inset-x-0 bottom-0 p-4 pb-[max(1rem,env(safe-area-inset-bottom))] bg-gradient-to-t from-black/85 via-black/50 to-transparent space-y-2">
          {phase === 'live' && quality && (
            <p className={`mx-auto w-fit rounded-full px-3 py-1 text-sm font-medium ${quality.ok ? 'bg-leaf/90' : 'bg-ochre/90 text-soil-dark'}`}>
              {quality.ok ? t('liveKeep') : quality.hint_text}
            </p>
          )}
          {liveTop && phase === 'live' && (
            <p className="mx-auto w-fit flex items-center gap-1.5 rounded-full bg-black/60 px-3 py-1 text-xs">
              {liveTop.healthy ? <Leaf className="w-3.5 h-3.5 text-leaf" /> : <Eye className="w-3.5 h-3.5 text-ochre" />}
              {liveTop.name} · {Math.round(liveTop.confidence * 100)}%
            </p>
          )}
          {Object.keys(tally).length > 0 && (
            <p className="text-center text-[11px] text-white/80">
              {t('liveSeenSoFar')}: {Object.values(tally).map((x) => `${x.name} ×${x.n}`).join(' · ')}
            </p>
          )}
          <div className="flex justify-center">
            <button onClick={() => (phase === 'live' ? finish(false) : (stopCamera(), wsRef.current?.close(), setPhase('intro')))}
              className="min-h-[48px] px-6 rounded-full bg-ember text-white font-medium flex items-center gap-2">
              <X className="w-4 h-4" /> {t('liveEnd')}
            </button>
          </div>
        </div>

        {(phase === 'starting' || phase === 'finishing') && (
          <div className="absolute inset-0 bg-black/60 flex flex-col items-center justify-center gap-3">
            <Loader2 className="w-8 h-8 animate-spin text-ochre" />
            <p className="text-sm">{phase === 'starting' ? t('liveStarting') : t('liveAnalysing')}</p>
          </div>
        )}

        {ask && (
          <div className="absolute inset-x-3 bottom-3 rounded-3xl bg-leaf-deep p-4 shadow-2xl">
            <p className="text-[11px] uppercase tracking-wide text-cream/60">{t('liveAnswer')}</p>
            <p className="mt-1 text-lg font-semibold leading-snug">{ask.question}</p>
            <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
              {ask.candidates.map((c) => (
                <p key={c.id} className="rounded-xl bg-white/10 p-2"><span className="font-semibold">{c.name}</span><br />{c.signature}</p>
              ))}
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2">
              <button onClick={() => answer('yes')} className="min-h-[48px] rounded-2xl bg-cream text-soil-dark font-semibold">{t('yes')}</button>
              <button onClick={() => answer('no')} className="min-h-[48px] rounded-2xl bg-cream text-soil-dark font-semibold">{t('no')}</button>
              <button onClick={() => answer('unknown')} className="min-h-[48px] rounded-2xl border border-cream/40 font-medium text-sm">{t('cantTell')}</button>
            </div>
          </div>
        )}

        {expertChoice && (
          <div className="absolute inset-x-3 bottom-3 rounded-3xl bg-leaf-deep p-4 shadow-2xl">
            <p className="text-lg font-semibold leading-snug">{t('liveExpertAsk')}</p>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <button onClick={() => { setExpertChoice(false); finish(true) }} className="min-h-[48px] rounded-2xl bg-cream text-soil-dark font-semibold">{t('liveYesSend')}</button>
              <button onClick={() => { setExpertChoice(false); finish(false) }} className="min-h-[48px] rounded-2xl border border-cream/40 font-medium">{t('liveNoThanks')}</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

const VERDICT = {
  all_good: { tone: 'bg-leaf-deep text-cream', icon: CheckCircle2, key: 'verdict_all_good' },
  risk: { tone: 'bg-ochre text-soil-dark', icon: AlertTriangle, key: 'verdict_risk' },
  found: { tone: 'bg-ember text-white', icon: ShieldAlert, key: 'verdict_found' },
  check: { tone: 'bg-sky-700 text-white', icon: Stethoscope, key: 'verdict_check' },
  // The walk may only claim what the camera saw: not enough confident views of
  // the plant is its own answer, never "healthy" by default.
  unclear: { tone: 'bg-soil-dark text-cream', icon: ScanSearch, key: 'verdict_unclear' },
  no_model: { tone: 'bg-soil-dark text-cream', icon: CameraOff, key: 'verdict_no_model' },
} as const

const LEVEL_TONE = { high: 'ember', medium: 'ochre', low: 'neutral' } as const

function SummaryView({ s, onAgain, onDone }: { s: LiveSummary; onAgain: () => void; onDone: () => void }) {
  const { t, lang } = useFarmer()
  const v = VERDICT[s.verdict]
  const c = s.context
  const w = c.weather_now
  const ph = c.soil.ph
  const moist = c.soil.moisture
  const seenTargets = new Set(s.seen.map((x) => x.target))
  const [allRisks, setAllRisks] = useState(false)
  const pending = c.risks.filter((r) => !seenTargets.has(r.target))
  const risks = allRisks ? pending : pending.slice(0, 3)

  return (
    <div className="space-y-4">
      <section className={`rounded-3xl p-5 ${v.tone}`}>
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <v.icon className="w-8 h-8 shrink-0" />
            <div>
              <p className="text-[11px] uppercase tracking-wide opacity-70">{t('liveTitle')}</p>
              <h1 className="text-2xl font-semibold leading-tight">{t(v.key)}</h1>
            </div>
          </div>
          <ListenButton text={s.speech} lang={lang} label={t('listen')} stopLabel={t('stop')} compact tone="light" />
        </div>
        {(s.verdict === 'unclear' || s.verdict === 'no_model') && (
          <p className="mt-3 text-sm leading-snug opacity-90">
            {s.verdict === 'unclear' ? t('liveUnclearHint') : t('liveNoModelHint').replace('{crop}', c.crop.name)}
          </p>
        )}
        {s.verdict === 'unclear' && (
          <button onClick={onAgain}
            className="mt-4 w-full min-h-[48px] rounded-full bg-cream text-soil-dark text-sm font-semibold">
            {t('liveTryAgain')}
          </button>
        )}
        {c.location.far_from_farm && (
          <p className="mt-2 text-xs opacity-80">{t('liveFar').replace('{km}', String(c.location.km_from_farm))}</p>
        )}
      </section>

      <div className="grid grid-cols-2 gap-3">
        <Card className="p-3">
          <p className="text-[11px] uppercase tracking-wide text-soil-dark/50 flex items-center gap-1"><CloudSun className="w-3 h-3" /> {t('liveNow')}</p>
          {w?.temp_c != null ? (
            <>
              <p className="mt-1 text-2xl font-semibold">{Math.round(w.temp_c)}°C</p>
              <p className="text-xs text-soil-dark/70">{w.rh_pct}% · {w.text ?? ''}{w.rain_mm_1h ? ` · ${w.rain_mm_1h} mm` : ''}</p>
              <p className="mt-1 text-[10px] text-soil-dark/40">{w.source}</p>
            </>
          ) : <p className="mt-1 text-sm text-soil-dark/50">—</p>}
        </Card>
        <Card className="p-3">
          <p className="text-[11px] uppercase tracking-wide text-soil-dark/50">{t('liveNext')}</p>
          {c.forecast ? (
            <>
              <p className="mt-1 text-sm"><span className="font-semibold">{c.forecast.rain_mm} mm</span> {t('liveRain')}</p>
              <p className="text-xs text-soil-dark/70">{c.forecast.t_min != null ? `${Math.round(c.forecast.t_min)}–${Math.round(c.forecast.t_max ?? 0)}°C` : ''} · RH ≤{c.forecast.rh_max ?? '—'}%</p>
              <p className="mt-1 text-[10px] text-soil-dark/40">{c.forecast.source}</p>
            </>
          ) : <p className="mt-1 text-sm text-soil-dark/50">—</p>}
        </Card>
        <Card className="p-3">
          <p className="text-[11px] uppercase tracking-wide text-soil-dark/50 flex items-center gap-1"><Sprout className="w-3 h-3" /> {t('liveSoil')}</p>
          {ph ? (
            <>
              <p className="mt-1 text-sm"><span className="text-xl font-semibold">{t('livePh')} {ph.value}</span></p>
              <p className="text-xs text-soil-dark/70">{ph.band}</p>
              <Pill tone={ph.how === 'estimated' ? 'ochre' : 'leaf'} className="mt-1 !text-[10px]">{t(`how_${ph.how}`)}</Pill>
            </>
          ) : <p className="mt-1 text-sm text-soil-dark/50">—</p>}
          {moist && (
            <p className="mt-1.5 text-xs text-soil-dark/70">
              <Droplets className="inline w-3 h-3 -mt-0.5 mr-1" />{t('liveMoisture')} {moist.value_pct}%
              <span className="block text-[10px] text-soil-dark/40">{moist.how === 'measured' ? t('how_measured') : t('how_modelled')}</span>
            </p>
          )}
        </Card>
        <Card className="p-3">
          <p className="text-[11px] uppercase tracking-wide text-soil-dark/50 flex items-center gap-1"><Leaf className="w-3 h-3" /> {t('liveStage')}</p>
          <p className="mt-1 text-sm font-semibold">{c.crop.name}</p>
          <p className="text-xs text-soil-dark/70">{c.crop.stage_name} · {c.crop.das} {t('daysOld')}</p>
        </Card>
      </div>

      {s.seen.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold">{t('liveSeen')}</h2>
          {s.seen.map((x) => (
            <Card key={x.target} className="p-4 border-ember/30">
              <div className="flex items-center justify-between gap-2">
                <p className="font-semibold">{x.name}</p>
                <Pill tone="ember">{t('liveViews').replace('{n}', String(x.views))} · {Math.round(x.confidence * 100)}%</Pill>
              </div>
              {x.evidence && x.evidence.length > 0 && (
                <div className="mt-2 flex gap-2">
                  {x.evidence.map((u) => <img key={u} src={u} alt="" className="w-16 h-16 rounded-xl object-cover" />)}
                </div>
              )}
              {x.advisory && (
                <div className="mt-2 space-y-1.5 text-sm">
                  {x.advisory.what_to_avoid[0] && <p className="text-ember font-medium">✕ {x.advisory.what_to_avoid[0]}</p>}
                  {x.advisory.ladder.filter((r) => r.tier !== 'chemical').slice(0, 2).map((r, i) => (
                    <p key={i} className="text-soil-dark/80">• {r.action}</p>
                  ))}
                </div>
              )}
              <Link to={`/app/history/${x.problem_id}`} className="mt-2 inline-block text-sm text-leaf-deep font-medium underline underline-offset-2">
                {t('liveOpenAdvice')} →
              </Link>
            </Card>
          ))}
        </section>
      )}

      {s.possible.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold">{t('livePossible')}</h2>
          {s.possible.map((x) => (
            <Card key={x.target} className="p-3 flex items-center justify-between gap-2">
              <span className="text-sm font-medium">{x.name}</span>
              {x.case && <Pill tone="sky">~{x.case.eta_minutes} min</Pill>}
            </Card>
          ))}
        </section>
      )}

      {risks.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold flex items-center gap-1.5"><AlertTriangle className="w-4 h-4 text-ochre" /> {t('liveRisks')}</h2>
          {risks.map((r) => (
            <Card key={r.target + r.trigger} className="p-4">
              <div className="flex items-center justify-between gap-2">
                <p className="font-semibold">{r.name}</p>
                <Pill tone={LEVEL_TONE[r.level]}>{t(`level_${r.level}`)}</Pill>
              </div>
              <p className="mt-1 text-xs text-soil-dark/70">{r.reason}</p>
              {r.prevention.do.length > 0 && (
                <div className="mt-2">
                  <p className="text-[11px] uppercase tracking-wide text-leaf-deep font-semibold">{t('livePrevent')}</p>
                  {r.prevention.do.map((d, i) => <p key={i} className="text-sm">• {d}</p>)}
                  {r.prevention.avoid[0] && <p className="text-sm text-ember">✕ {r.prevention.avoid[0]}</p>}
                </div>
              )}
              {r.check.length > 0 && (
                <div className="mt-2">
                  <p className="text-[11px] uppercase tracking-wide text-soil-dark/50 font-semibold">{t('liveCheck')}</p>
                  {r.check.map((d, i) => <p key={i} className="text-xs text-soil-dark/80">• {d}</p>)}
                </div>
              )}
              {r.prevention.icar.length > 0 && <p className="mt-2 text-[11px] text-leaf-deep">ICAR: {r.prevention.icar.join(' · ')}</p>}
            </Card>
          ))}
          {pending.length > risks.length && (
            <button onClick={() => setAllRisks(true)} className="w-full min-h-[44px] rounded-full border border-soil-dark/15 bg-white text-sm">
              {t('liveMoreRisks').replace('{n}', String(pending.length - risks.length))}
            </button>
          )}
        </section>
      )}

      <p className="text-[11px] text-soil-dark/50 text-center">
        {t('liveStats').replace('{f}', String(s.stats.frames)).replace('{c}', String(s.stats.classified_views))}
        {s.photo_model ? ` · ${s.model_version}` : ''}
      </p>
      <div className="grid grid-cols-2 gap-2">
        <button onClick={onAgain} className="min-h-[48px] rounded-full border border-soil-dark/20 bg-white text-sm font-medium">{t('liveAgain')}</button>
        <button onClick={onDone} className="min-h-[48px] rounded-full bg-leaf-deep text-cream text-sm font-medium">{t('liveDone')}</button>
      </div>
    </div>
  )
}
