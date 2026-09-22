import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { driver, type Driver, type DriveStep, type PopoverDOM } from 'driver.js'
import 'driver.js/dist/driver.css'
import './tour.css'
import { Headphones } from 'lucide-react'
import { useAuth } from '../../auth/AuthContext'
import { useFarmer } from '../FarmerContext'
import { AFTER_VOICE_MS, NEW_ACCOUNT_DAYS, readingMs, TOUR_MUTED_KEY, TOUR_STEPS, tourSeenKey } from './steps'

// The spoken app tour. driver.js draws the spotlight and the card; this adds
// the voice — one clip per step in the farmer's language (public/tour, made by
// backend/make_tour_audio.py) — and the pace: left alone, a step stays until
// its voice has finished (or, muted, its reading time has passed) and then the
// tour moves on by itself, so a farmer who cannot read can simply listen.
// Next and Back work at any time.

const store = {
  get: (k: string) => { try { return localStorage.getItem(k) } catch { return null } },
  set: (k: string, v: string) => { try { localStorage.setItem(k, v) } catch { /* private mode */ } },
}

const Ctx = createContext<{ start: () => void }>({ start: () => undefined })
export const useTour = () => useContext(Ctx)

export function TourProvider({ children }: { children: ReactNode }) {
  const { t, lang, farmId } = useFarmer()
  const { me } = useAuth()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const tour = useRef<Driver | null>(null)
  // One audio element for the whole tour: it is first played inside the tap
  // that started the tour, which is what lets phones (iOS above all) keep
  // playing each next clip without a fresh tap.
  const audio = useRef<HTMLAudioElement | null>(null)
  const muted = useRef(store.get(TOUR_MUTED_KEY) === '1')
  const where = useRef(pathname)
  useEffect(() => { where.current = pathname }, [pathname])
  const [asking, setAsking] = useState(false)

  // The step on screen: its popover's parts, and a token so a late 'ended'
  // from a previous step's clip can never move the tour on.
  const live = useRef<{ pop?: PopoverDOM; token: number; timer?: number; done: boolean }>({ token: 0, done: false })

  const seenKey = tourSeenKey(me?.id)

  // A new account (or a demo one) is asked once, as soon as its farm opens.
  useEffect(() => {
    if (!me || farmId == null || store.get(seenKey) === '1') return
    const age = me.created_at ? (Date.now() - Date.parse(me.created_at)) / 864e5 : Infinity
    if (me.is_demo || age <= NEW_ACCOUNT_DAYS) setAsking(true)
  }, [me, farmId, seenKey])

  const bar = (pct: number) => {
    const fill = live.current.pop?.wrapper.querySelector<HTMLElement>('.ar-tour-bar > span')
    if (fill) fill.style.width = `${Math.min(100, pct)}%`
  }

  /** The step's voice (or reading time) is over: move on by itself. Next is
   *  never locked — a farmer can skip ahead to the part they want. */
  const finish = useCallback((token: number) => {
    const s = live.current
    if (token !== s.token || s.done) return
    s.done = true
    bar(100)
    if (tour.current?.isLastStep()) return // the last step waits for Finish
    s.timer = window.setTimeout(() => { if (token === live.current.token) tour.current?.moveNext() }, AFTER_VOICE_MS)
  }, [])

  /** Play step `index`. `again` (sound toggled, or play again) keeps a step
   *  already heard unlocked — the farmer is never made to wait twice. */
  const speak = useCallback((index: number, again = false) => {
    const s = live.current
    window.clearTimeout(s.timer)
    const token = ++s.token
    if (!again) { s.done = false; bar(0) }
    const step = TOUR_STEPS[index]
    const a = audio.current
    const text = `${t(`tour_${step.id}_t`)} ${t(`tour_${step.id}_b`)}`
    const quiet = () => { // muted, or the clip will not play: wait the reading time instead
      if (live.current.done) return
      const began = performance.now(), ms = readingMs(text)
      const tick = () => {
        if (token !== live.current.token || live.current.done) return
        const pct = ((performance.now() - began) / ms) * 100
        bar(pct)
        if (pct >= 100) finish(token)
        else requestAnimationFrame(tick)
      }
      requestAnimationFrame(tick)
    }
    if (!a || muted.current) { a?.pause(); quiet(); return }
    a.pause()
    a.src = `/tour/${lang}/${step.id}.mp3`
    a.ontimeupdate = () => {
      if (token === live.current.token && !live.current.done && a.duration) bar((a.currentTime / a.duration) * 100)
    }
    a.onended = () => finish(token)
    a.onerror = () => { if (token === live.current.token) quiet() }
    void a.play().catch(() => { if (token === live.current.token) quiet() })
  }, [finish, lang, t])

  const stop = () => {
    live.current.token++
    window.clearTimeout(live.current.timer)
    audio.current?.pause()
  }

  const start = useCallback(() => {
    setAsking(false)
    store.set(seenKey, '1')
    tour.current?.destroy()
    // Unlock audio inside this tap (see `audio` above).
    audio.current ??= new Audio()
    audio.current.src = `/tour/${lang}/welcome.mp3`
    if (!muted.current) void audio.current.play().catch(() => undefined)

    const steps: DriveStep[] = TOUR_STEPS.map((s) => ({
      element: s.target ? `[data-tour="${s.target}"]` : undefined,
      waitForElement: s.target ? 5000 : undefined,
      skipMissingElement: true, // a card that is not on screen (no weather yet) is skipped, not waited on forever
      disableActiveInteraction: !s.tap,
      advanceOnClick: Boolean(s.tap),
      popover: { title: t(`tour_${s.id}_t`), description: t(`tour_${s.id}_b`), side: s.side, align: 'center' },
    }))

    const controls = (pop: PopoverDOM, index: number) => {
      live.current.pop = pop
      const progress = document.createElement('div')
      progress.className = 'ar-tour-bar'
      progress.setAttribute('aria-hidden', 'true')
      progress.append(document.createElement('span'))
      const row = document.createElement('div')
      row.className = 'ar-tour-audio'
      const sound = document.createElement('button')
      const replay = document.createElement('button')
      const label = () => {
        sound.textContent = muted.current ? t('tourUnmute') : t('tourMute')
        sound.classList.toggle('ar-tour-playing', !muted.current)
        sound.setAttribute('aria-pressed', String(muted.current))
      }
      label()
      sound.onclick = () => {
        muted.current = !muted.current
        store.set(TOUR_MUTED_KEY, muted.current ? '1' : '0')
        label()
        speak(index, true)
      }
      replay.textContent = t('tourReplay')
      replay.onclick = () => {
        if (muted.current) { muted.current = false; store.set(TOUR_MUTED_KEY, '0'); label() }
        speak(index, true)
      }
      row.append(sound, replay)
      pop.footer.prepend(progress, row)
    }

    const run = () => {
      tour.current = driver({
        steps,
        showProgress: true,
        progressText: t('tourProgress').replace('{n}', '{{current}}').replace('{total}', '{{total}}'),
        nextBtnText: `${t('tourNext')} →`,
        prevBtnText: `← ${t('tourBack')}`,
        doneBtnText: t('tourDone'),
        popoverClass: 'ar-tour',
        overlayColor: '#1b140d',
        overlayOpacity: 0.62,
        stagePadding: 6,
        stageRadius: 18,
        smoothScroll: true,
        allowClose: true,
        onPopoverRender: (pop, { index }) => controls(pop, index ?? 0),
        onHighlighted: (_el, _step, { index }) => speak(index ?? 0),
        onDeselected: () => stop(),
        onDestroyed: () => stop(),
      })
      tour.current.drive()
    }
    // The tour explains Home first: open it, then start once it has drawn.
    if (where.current !== '/app' && where.current !== '/app/') {
      navigate('/app')
      window.setTimeout(run, 350)
    } else run()
  }, [lang, navigate, seenKey, speak, t])

  useEffect(() => () => { tour.current?.destroy(); audio.current?.pause() }, [])

  const later = () => {
    store.set(seenKey, '1')
    setAsking(false)
  }

  return (
    <Ctx.Provider value={{ start }}>
      {children}
      {asking && (
        <div className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center bg-soil-dark/55 p-4 animate-fadein"
          role="dialog" aria-modal="true" aria-labelledby="tour-ask-title">
          <section className="relative w-full max-w-md rounded-3xl bg-leaf-deep text-cream p-6 overflow-hidden shadow-2xl">
            <span aria-hidden className="absolute -right-10 -top-12 w-44 h-44 rounded-full bg-ochre/25 blur-2xl" />
            <span className="relative w-14 h-14 rounded-2xl bg-cream/10 ring-1 ring-ochre/50 flex items-center justify-center">
              <Headphones className="w-7 h-7 text-ochre" />
            </span>
            <h2 id="tour-ask-title" className="relative mt-4 text-xl font-semibold leading-snug">{t('tourInviteTitle')}</h2>
            <p className="relative mt-1.5 text-[15px] text-cream/75 leading-snug">{t('tourInviteBody')}</p>
            <div className="relative mt-6 flex gap-2">
              <button onClick={start} autoFocus
                className="flex-1 min-h-[50px] rounded-full bg-ochre text-soil-dark text-[15px] font-semibold hover:brightness-105">
                {t('tourStart')}
              </button>
              <button onClick={later} className="min-h-[50px] px-6 rounded-full border border-cream/25 text-[15px] font-medium hover:bg-cream/10">
                {t('tourLater')}
              </button>
            </div>
          </section>
        </div>
      )}
    </Ctx.Provider>
  )
}

/** The way back into the tour, any time: the sidebar on a wide screen
 *  (`variant="sidebar"`), the foot of Home on a phone (`variant="row"`). */
export function TourButton({ variant }: { variant: 'sidebar' | 'row' }) {
  const { t } = useFarmer()
  const { start } = useTour()
  if (variant === 'sidebar') {
    return (
      <button onClick={start}
        className="hidden lg:flex mx-4 mt-auto mb-2 items-center gap-2.5 rounded-xl bg-ochre/15 border border-ochre/30 px-3 py-2.5 text-left text-[13px] font-medium text-cream hover:bg-ochre/25">
        <Headphones className="w-4 h-4 shrink-0 text-ochre" />
        <span className="flex-1">{t('tourMenu')}</span>
      </button>
    )
  }
  return (
    <button onClick={start}
      className="lg:hidden w-full mb-16 flex items-center gap-3 rounded-2xl bg-white border border-soil-dark/10 p-3 text-left hover:border-leaf/40">
      <span className="shrink-0 w-10 h-10 rounded-xl bg-leaf-deep/10 flex items-center justify-center">
        <Headphones className="w-5 h-5 text-leaf-deep" />
      </span>
      <span className="flex-1 min-w-0">
        <span className="block text-sm font-semibold">{t('tourMenu')}</span>
        <span className="block text-xs text-soil-dark/55">{t('tourInviteBody')}</span>
      </span>
      <span className="text-leaf-deep">→</span>
    </button>
  )
}
