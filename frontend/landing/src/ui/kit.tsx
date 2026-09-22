import { useEffect, useRef, useState, type HTMLAttributes, type ReactNode } from 'react'
import { AlertTriangle, Loader2, Mic, Square, Volume2, WifiOff } from 'lucide-react'
import { api } from '../api/client'
import type { Heatmap, Lang } from '../api/types'

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-soil-dark/60">
      <Loader2 className="w-4 h-4 animate-spin" />
      {label}
    </div>
  )
}

export function ErrorBox({ error, onRetry, retryLabel = 'Retry' }: {
  error: Error; onRetry?: () => void; retryLabel?: string
}) {
  const offline = error.message === 'offline'
  return (
    <div className="rounded-2xl border border-ember/30 bg-ember/5 p-4 flex gap-3 items-start">
      {offline ? <WifiOff className="w-5 h-5 text-ember shrink-0" /> : <AlertTriangle className="w-5 h-5 text-ember shrink-0" />}
      <div className="flex-1 text-sm">
        <p className="text-soil-dark/80">{offline ? 'Cannot reach the AnnRakshak server.' : error.message}</p>
        {onRetry && (
          <button onClick={onRetry} className="mt-2 text-ember font-medium underline underline-offset-2">
            {retryLabel}
          </button>
        )}
      </div>
    </div>
  )
}

export function Pill({ children, tone = 'neutral', className = '' }: {
  children: ReactNode; tone?: 'neutral' | 'leaf' | 'ochre' | 'ember' | 'sky' | 'dark'; className?: string
}) {
  const tones = {
    neutral: 'bg-soil-dark/5 text-soil-dark/70',
    leaf: 'bg-leaf/15 text-leaf-deep',
    ochre: 'bg-ochre/15 text-[#8a5a17]',
    ember: 'bg-ember/10 text-ember',
    sky: 'bg-sky-100 text-sky-800',
    dark: 'bg-leaf-deep text-cream',
  }
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium ${tones[tone]} ${className}`}>
      {children}
    </span>
  )
}

export function Card({ children, className = '', ...rest }: { children: ReactNode; className?: string } & Omit<HTMLAttributes<HTMLDivElement>, 'className' | 'children'>) {
  return <div {...rest} className={`rounded-2xl bg-white border border-soil-dark/10 ${className}`}>{children}</div>
}

/** Reads text aloud with Sarvam Bulbul via the backend (key stays server-side). */
export function ListenButton({ text, lang, label, stopLabel, compact = false, tone = 'dark' }: {
  text: string; lang: Lang; label: string; stopLabel: string; compact?: boolean; tone?: 'dark' | 'light'
}) {
  const [state, setState] = useState<'idle' | 'loading' | 'playing' | 'error'>('idle')
  const audio = useRef<HTMLAudioElement | null>(null)
  const url = useRef<string | null>(null)

  useEffect(() => () => {
    audio.current?.pause()
    if (url.current) URL.revokeObjectURL(url.current)
  }, [])

  const toggle = async () => {
    if (state === 'playing') {
      audio.current?.pause()
      setState('idle')
      return
    }
    setState('loading')
    try {
      const blob = await api.tts(text, lang)
      if (url.current) URL.revokeObjectURL(url.current)
      url.current = URL.createObjectURL(blob)
      audio.current = new Audio(url.current)
      audio.current.onended = () => setState('idle')
      await audio.current.play()
      setState('playing')
    } catch {
      setState('error')
      setTimeout(() => setState('idle'), 2500)
    }
  }

  return (
    <button
      onClick={toggle}
      aria-label={state === 'playing' ? stopLabel : label}
      className={`inline-flex items-center justify-center gap-1.5 rounded-full font-medium transition-colors ${
        compact ? 'w-9 h-9' : 'min-h-[40px] px-3.5 text-xs'
      } ${state === 'playing' ? 'bg-ochre text-cream' : state === 'error' ? 'bg-ember/10 text-ember' : tone === 'light' ? 'bg-cream text-leaf-deep' : 'bg-leaf-deep text-cream'}`}
    >
      {state === 'loading' ? <Loader2 className="w-4 h-4 animate-spin" /> : state === 'playing' ? <Square className="w-3.5 h-3.5" /> : <Volume2 className="w-4 h-4" />}
      {!compact && (state === 'playing' ? stopLabel : label)}
    </button>
  )
}

/** Push-to-talk with Sarvam Saaras via the backend. */
export function VoiceButton({ lang, onText, label, recordingLabel, compact = false }: {
  lang: Lang; onText: (t: string) => void; label: string; recordingLabel: string; compact?: boolean
}) {
  const [state, setState] = useState<'idle' | 'recording' | 'busy' | 'error'>('idle')
  const rec = useRef<MediaRecorder | null>(null)

  const start = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const chunks: Blob[] = []
      const r = new MediaRecorder(stream)
      r.ondataavailable = (e) => chunks.push(e.data)
      r.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        setState('busy')
        try {
          const { transcript } = await api.stt(new Blob(chunks, { type: r.mimeType }), lang)
          onText(transcript.trim())
          setState('idle')
        } catch {
          setState('error')
          setTimeout(() => setState('idle'), 2500)
        }
      }
      rec.current = r
      r.start()
      setState('recording')
      setTimeout(() => r.state === 'recording' && r.stop(), 15000)
    } catch {
      setState('error')
      setTimeout(() => setState('idle'), 2500)
    }
  }

  return (
    <button
      type="button"
      onClick={() => (state === 'recording' ? rec.current?.stop() : state === 'idle' && start())}
      aria-label={state === 'recording' ? recordingLabel : label}
      className={`inline-flex items-center justify-center gap-1.5 rounded-xl text-sm font-medium border transition-colors ${
        compact ? 'w-11 h-11 shrink-0' : 'min-h-[48px] px-4'} ${
        state === 'recording' ? 'bg-ember text-cream border-ember animate-pulse' : 'bg-white border-soil-dark/20 text-soil-dark'
      }`}
    >
      {state === 'busy' ? <Loader2 className="w-4 h-4 animate-spin" /> : state === 'recording' ? <Square className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
      {!compact && (state === 'recording' ? recordingLabel : label)}
    </button>
  )
}

const FLOOR = 0.4
const GATE = 0.7

/** Confidence with the gate's own thresholds drawn on it, so the farmer can see
 *  why the app advised, asked or escalated. */
export function ConfidenceMeter({ value, label, askLabel = 'ask', adviseLabel = 'advise' }: {
  value: number; label: string; askLabel?: string; adviseLabel?: string
}) {
  const pct = Math.round(value * 100)
  const tone = value >= GATE ? 'bg-leaf' : value >= FLOOR ? 'bg-ochre' : 'bg-ember'
  return (
    <div>
      <div className="flex items-baseline justify-between text-xs mb-1">
        <span className="font-semibold text-soil-dark">{pct}% {label}</span>
      </div>
      <div className="relative h-2.5 rounded-full bg-soil-dark/10 overflow-visible">
        <div className={`h-full rounded-full ${tone} transition-all duration-700`} style={{ width: `${pct}%` }} />
        {[FLOOR, GATE].map((m) => (
          <span key={m} className="absolute -top-1 h-4.5 w-px bg-soil-dark/40" style={{ left: `${m * 100}%`, height: 18 }} />
        ))}
      </div>
      <div className="relative h-4 text-[10px] text-soil-dark/40">
        <span className="absolute -translate-x-1/2" style={{ left: `${FLOOR * 100}%` }}>{askLabel}</span>
        <span className="absolute -translate-x-1/2" style={{ left: `${GATE * 100}%` }}>{adviseLabel}</span>
      </div>
    </div>
  )
}

function jet(v: number): [number, number, number] {
  const r = Math.min(1, Math.max(0, 1.5 - Math.abs(4 * v - 3)))
  const g = Math.min(1, Math.max(0, 1.5 - Math.abs(4 * v - 2)))
  const b = Math.min(1, Math.max(0, 1.5 - Math.abs(4 * v - 1)))
  return [r * 255, g * 255, b * 255]
}

/** Real Grad-CAM from the model, drawn on a canvas over the photo. */
export function GradCamOverlay({ heatmap, opacity = 0.45 }: { heatmap: Heatmap; opacity?: number }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const c = ref.current
    if (!c) return
    const { grid, rows, cols } = heatmap
    c.width = cols
    c.height = rows
    const ctx = c.getContext('2d')!
    const img = ctx.createImageData(cols, rows)
    for (let y = 0; y < rows; y++) {
      for (let x = 0; x < cols; x++) {
        const v = grid[y][x]
        const [r, g, b] = jet(v)
        const i = (y * cols + x) * 4
        img.data[i] = r
        img.data[i + 1] = g
        img.data[i + 2] = b
        img.data[i + 3] = Math.round(255 * Math.min(1, v * 1.2) * opacity)
      }
    }
    ctx.putImageData(img, 0, 0)
  }, [heatmap, opacity])
  return (
    <canvas
      ref={ref}
      aria-hidden
      className="absolute inset-0 w-full h-full pointer-events-none"
      style={{ imageRendering: 'auto', filter: 'blur(6px)' }}
    />
  )
}

export function SectionTitle({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <div className="mb-3">
      <h2 className="font-instrument-serif text-2xl leading-tight text-soil-dark">{children}</h2>
      {sub && <p className="text-xs text-soil-dark/60 mt-0.5">{sub}</p>}
    </div>
  )
}
