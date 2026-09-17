import { api } from '../api/client'
import type { Lang } from '../api/types'

const BCP47: Record<Lang, string> = {
  en: 'en-IN', hi: 'hi-IN', mr: 'mr-IN', bn: 'bn-IN', ta: 'ta-IN', te: 'te-IN', kn: 'kn-IN', ml: 'ml-IN',
  gu: 'gu-IN', pa: 'pa-IN', od: 'or-IN',
}

export function browserVoice(lang: Lang): SpeechSynthesisVoice | null {
  if (!('speechSynthesis' in window)) return null
  const want = BCP47[lang].toLowerCase()
  const voices = window.speechSynthesis.getVoices()
  return voices.find((v) => v.lang.toLowerCase() === want)
    ?? voices.find((v) => v.lang.toLowerCase().startsWith(want.slice(0, 2)))
    ?? null
}

/**
 * Speaks guidance during the live walk. Sarvam voices (server-side, cached per
 * text) with the browser's own speech as a fallback. A new prompt interrupts
 * the current one; coaching hints are throttled and never cut off a prompt.
 */
export class Speaker {
  private audio: HTMLAudioElement | null = null
  private cache = new Map<string, Promise<string>>()
  private speakingPrompt = false
  private lastHintAt = 0
  muted = false
  private lang: Lang

  /** The farmer switched language mid-call: speak the new one from now on. */
  setLang(lang: Lang) {
    this.lang = lang
  }

  constructor(lang: Lang) {
    this.lang = lang
  }

  private url(text: string): Promise<string> {
    const key = `${this.lang}|${text}`
    let p = this.cache.get(key)
    if (!p) {
      p = api.tts(text, this.lang).then((b) => URL.createObjectURL(b))
      p.catch(() => this.cache.delete(key))
      this.cache.set(key, p)
    }
    return p
  }

  /** Warm the cache so the first prompt of each step starts instantly. */
  preload(texts: string[]) {
    texts.forEach((t) => void this.url(t).catch(() => undefined))
  }

  stop() {
    this.audio?.pause()
    this.audio = null
    if ('speechSynthesis' in window) window.speechSynthesis.cancel()
    this.speakingPrompt = false
  }

  async prompt(text: string) {
    if (this.muted || !text) return
    this.stop()
    this.speakingPrompt = true
    await this.play(text)
    this.speakingPrompt = false
  }

  async hint(text: string, minGapMs = 7000) {
    if (this.muted || !text || this.speakingPrompt) return
    const now = Date.now()
    if (now - this.lastHintAt < minGapMs) return
    this.lastHintAt = now
    await this.play(text)
  }

  private async play(text: string) {
    try {
      const src = await this.url(text)
      await new Promise<void>((resolve) => {
        const a = new Audio(src)
        this.audio = a
        a.onended = () => resolve()
        a.onerror = () => resolve()
        a.play().catch(() => resolve())
      })
    } catch {
      // Browser speech only with a voice for this language: an English voice
      // reading Marathi or Hindi text is worse than silence.
      const voice = browserVoice(this.lang)
      if (!voice) return
      await new Promise<void>((resolve) => {
        const u = new SpeechSynthesisUtterance(text)
        u.lang = BCP47[this.lang]
        u.voice = voice
        u.onend = () => resolve()
        u.onerror = () => resolve()
        window.speechSynthesis.speak(u)
      })
    }
  }

  dispose() {
    this.stop()
    for (const p of this.cache.values()) p.then((u) => URL.revokeObjectURL(u)).catch(() => undefined)
    this.cache.clear()
  }
}
