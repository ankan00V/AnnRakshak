import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Bell, Camera, CloudSun, FlaskConical, Headphones, Home as HomeIcon, LandPlot, Search, X } from 'lucide-react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { Farm, Lang, LiveEvent } from '../api/types'
import { useWide } from '../lib/hooks'
import { registerWorker } from '../lib/push'
import { EVENT as OUTBOX_EVENT, startOutbox, type OutboxChange } from '../lib/outbox'
import { FarmerProvider, useFarmer } from './FarmerContext'
import { TourProvider, useTour } from './tour/Tour'
import LanguagePicker from './components/LanguagePicker'
import Onboard from './screens/Onboard'
import BrandMark from '../ui/BrandMark'
import AccountMenu from '../auth/AccountMenu'
import { useAuth } from '../auth/AuthContext'
import Krishi from '../krishi/Krishi'
import { askKrishi } from '../krishi/bus'
import { photoSrcSet } from './fieldPhoto'
import { hideBroken } from './ui'

/** The phone's bottom bar: the five things a farmer does most. */
const NAV = [
  { to: '/app', icon: HomeIcon, key: 'home' },
  { to: '/app/weather', icon: CloudSun, key: 'weatherNav' },
  { to: '/app/scan', icon: Camera, key: 'scan' },
  { to: '/app/spray', icon: FlaskConical, key: 'spray' },
  { to: '/app/alerts', icon: Bell, key: 'alerts' },
]

/** The desktop sidebar: the phone's tab bar, and the farmer's fields under it
 *  (on a phone the field card's place name opens the same list). Krishi has
 *  its own button. */
const SIDE = [
  { to: '/app', icon: HomeIcon, key: 'home' },
  { to: '/app/weather', icon: CloudSun, key: 'weatherNav' },
  { to: '/app/scan', icon: Camera, key: 'navScan' },
  { to: '/app/spray', icon: FlaskConical, key: 'spray' },
  { to: '/app/alerts', icon: Bell, key: 'alerts' },
  { to: '/app/fields', icon: LandPlot, key: 'navFields' },
] as const

/** A language the farmer picked while the server could not be reached, still
 *  to be saved on their field. Without it the next online open would read the
 *  field's old language back and undo the farmer's choice. */
const LANG_PENDING = 'ar.langPending'
type PendingLang = { farm: number; lang: Lang }
function readPending(): PendingLang | null {
  try {
    const raw = localStorage.getItem(LANG_PENDING)
    const p = raw ? (JSON.parse(raw) as PendingLang) : null
    return p && typeof p.farm === 'number' && typeof p.lang === 'string' ? p : null
  } catch {
    return null
  }
}
function writePending(p: PendingLang | null) {
  try {
    if (p) localStorage.setItem(LANG_PENDING, JSON.stringify(p))
    else localStorage.removeItem(LANG_PENDING)
  } catch {
    /* private mode: the change is still applied on this phone */
  }
}
/** Save a language on a field. Only a lost connection is kept to try again: a
 *  refusal (a shared demo field) would be refused every time. */
async function saveLang(farm: number, lang: Lang): Promise<void> {
  try {
    await api.setFarmLang(farm, lang)
    const p = readPending()
    if (p && p.farm === farm && p.lang === lang) writePending(null)
  } catch (e) {
    if (e instanceof ApiError && e.status === 0) writePending({ farm, lang })
    else {
      // Only this field's entry: an offline change for another field must still go.
      const p = readPending()
      if (p && p.farm === farm) writePending(null)
    }
  }
}

function Shell() {
  const { lang, setLang, farmId, setFarmId, t, unread, setUnread, setToast } = useFarmer()
  const { me } = useAuth()
  const { pathname } = useLocation()
  const { start: startTour } = useTour()
  // Tab screens use the full desktop grid; detail screens stay at reading width.
  const wideRoute = ['/app', '/app/', '/app/weather', '/app/scan', '/app/spray', '/app/alerts', '/app/history', '/app/profile', '/app/result', '/app/live', '/app/fields']
    .includes(pathname) || pathname.startsWith('/app/history/')
  const home = pathname === '/app' || pathname === '/app/'
  const [farm, setFarm] = useState<Farm | null>(null)
  const synced = useRef<number | null>(null)
  const wide = useWide()
  // Read, not depended on: the field list is fetched once per field, not again
  // on every language change (which, when the field's language differed from
  // the phone's, fetched it twice and reopened the live connection twice).
  const langRef = useRef(lang)
  useEffect(() => { langRef.current = lang }, [lang])

  useEffect(() => {
    if (farmId == null) return
    let on = true
    api.farms(langRef.current).then((fs) => {
      if (!on) return
      const f = fs.find((x) => x.id === farmId) ?? null
      setFarm(f)
      if (!f) setFarmId(null) // stale id from an older database
      // The farmer's saved language wins when their own farm opens on this
      // device. A demo farm is a showcase: the viewer keeps the language they chose.
      if (f && !f.is_demo && synced.current !== f.id) {
        synced.current = f.id
        const pending = readPending()
        // A change made offline is newer than what the server holds: send it
        // instead of letting the server's copy overwrite it.
        if (pending && pending.farm === f.id) void saveLang(f.id, pending.lang)
        else if (f.lang !== langRef.current) setLang(f.lang)
      }
    }).catch(() => undefined)
    return () => {
      on = false
    }
  }, [farmId, setFarmId, setLang])

  // Signal back: save the language the farmer picked while it was gone.
  useEffect(() => {
    const retry = () => {
      const p = readPending()
      if (p) void saveLang(p.farm, p.lang)
    }
    window.addEventListener('online', retry)
    return () => window.removeEventListener('online', retry)
  }, [])

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])

  useEffect(() => {
    void registerWorker()
  }, [])

  // Photos taken without signal (Scan keeps them) go the moment there is one;
  // the farmer is told when the answer is back, wherever they are in the app.
  const tRef = useRef(t)
  useEffect(() => { tRef.current = t }, [t])
  useEffect(() => startOutbox((q) => api.diagnose(q.farmId, q.blob, q.lang, undefined, q.id)), [])
  useEffect(() => {
    const changed = (e: Event) => {
      const sent = (e as CustomEvent<OutboxChange>).detail?.sent
      if (!sent) return
      setToast({
        type: 'notice', id: sent.result.problem_id, severity: 'info',
        title: tRef.current('scanSentTitle'), body: tRef.current('scanSentBody'),
        url: `/app/history/${sent.result.problem_id}`,
      })
    }
    window.addEventListener(OUTBOX_EVENT, changed)
    return () => window.removeEventListener(OUTBOX_EVENT, changed)
  }, [setToast])

  // Real-time: new weather notices and field alerts while the app is open.
  // The stream is the same in every language, so a language change does not
  // reconnect it; only the count is read, in whatever language is current.
  useEffect(() => {
    if (farmId == null) return
    api.notices(farmId, langRef.current).then((n) => setUnread(n.unread)).catch(() => undefined)
    const es = new EventSource(`/api/farms/${farmId}/events`)
    const on = (ev: MessageEvent) => {
      try {
        const e = JSON.parse(ev.data) as LiveEvent
        setToast(e)
        if (e.type === 'notice') setUnread((n) => n + 1)
      } catch {
        /* ignore a malformed event */
      }
    }
    es.addEventListener('notice', on)
    es.addEventListener('alert', on)
    es.addEventListener('verdict', on)   // an expert answered a case this farm sent
    es.addEventListener('followup', on)  // the day-4 check on a treatment is due
    return () => es.close()
  }, [farmId, setUnread, setToast])

  const active = pathname === '/app/fields'
    ? '/app/fields'
    : pathname === '/app/result' || pathname === '/app/live'
    ? '/app/scan'
    : pathname.startsWith('/app/history')
      ? '/app'
      : NAV.slice().reverse().find((n) => pathname === n.to || pathname.startsWith(n.to + '/'))?.to ?? '/app'
  // The tab just tapped lights at once. The router keeps the old screen up
  // while the next one's code downloads, which on 2G is seconds of a tap that
  // looks ignored; the highlight lasts until the route actually changes, and
  // is then dropped, so Back to the old screen does not re-light the old tap.
  // Dropped during render (not in an effect), so no frame lights the old tap.
  const [tapped, setTapped] = useState<{ to: string } | null>(null)
  const [tappedAt, setTappedAt] = useState(pathname)
  if (tappedAt !== pathname) {
    setTappedAt(pathname)
    setTapped(null)
  }
  const lit = tapped ? tapped.to : active

  const first = (me?.name ?? '').trim().split(/\s+/)[0] ?? ''
  // Each tab screen opens with one line saying what it is for, in the place
  // the greeting has on Home. Gated on the chosen field, not the fetched one:
  // offline or still loading, the screen keeps its h1 (Profile picks its own
  // h1/h2 by the same test).
  const heading = farmId == null ? null
    : home ? { title: <>{t('greetHello').replace('{name}', first)} <span aria-hidden>👋</span></>, sub: t('greetSub') }
      : pathname === '/app/weather' ? { title: t('weatherTitle'), sub: t('wxPageSub') }
        : pathname === '/app/scan' ? { title: t('navScan'), sub: t('scanPageSub') }
          : pathname === '/app/spray' ? { title: t('sprayTitle'), sub: t('spraySub') }
            : pathname === '/app/alerts' ? { title: t('alertsTitle'), sub: t('alertsPageSub') }
              : pathname === '/app/history' ? { title: t('historyTitle'), sub: t('historySub') }
                : pathname === '/app/profile' ? { title: t('profileTitle'), sub: t('profileSub') }
                  : null
  const controls = (
    <div className="flex items-center gap-2">
      <button onClick={() => askKrishi()} aria-label={t('krishiAsk')}
        className="hidden sm:flex w-11 h-11 rounded-full bg-white items-center justify-center text-soil-dark shadow-[0_4px_14px_-8px_rgba(43,29,18,0.35)] ring-1 ring-soil-dark/5 hover:bg-cream active:bg-cream transition-colors">
        <Search className="w-[18px] h-[18px]" aria-hidden />
      </button>
      <LanguagePicker light onPick={(code) => {
        setLang(code)
        if (farmId != null) void saveLang(farmId, code)
      }} />
      {farm && (
        // The red dot is hidden from a screen reader, so the label carries the count.
        <Link to="/app/alerts" aria-label={unread > 0 ? `${t('noticesTitle')} (${unread})` : t('noticesTitle')}
          className="relative w-11 h-11 rounded-full bg-white flex items-center justify-center text-soil-dark shadow-[0_4px_14px_-8px_rgba(43,29,18,0.35)] ring-1 ring-soil-dark/5 hover:bg-cream active:bg-cream transition-colors">
          <Bell className="w-[18px] h-[18px]" aria-hidden />
          {unread > 0 && <span className="absolute top-2 right-2.5 w-2.5 h-2.5 rounded-full bg-ember ring-2 ring-white" aria-hidden />}
        </Link>
      )}
      <AccountMenu light logoutLabel={t('authLogout')} demoLabel={t('demoFarm')}
        profile={{ to: '/app/profile', label: t('profileMenu') }}
        privacy={{
          yourData: t('yourData'), downloadData: t('downloadData'),
          deleteAccount: t('deleteAccount'), deleteWhat: t('deleteWhat'),
          typeToConfirm: t('deleteTypeToConfirm'), confirmWord: t('deleteConfirmWord'),
          forever: t('deleteForever'), cancel: t('deleteCancel'), done: t('deleteDone'),
          what: t('privacyWhat'), phone: t('privacyPhone'), cookie: t('privacyCookie'),
          noAds: t('privacyNoAds'), server: t('privacyServer'),
        }}
        extra={farm ? { label: t('tourMenu'), onClick: startTour } : undefined} />
    </div>
  )

  return (
    <div className="relative min-h-screen w-full bg-cream text-soil-dark">
      {/* The morning behind the greeting: hills over the paddy, fading into the page. */}
      <div aria-hidden className={`pointer-events-none absolute inset-x-0 top-0 h-[300px] overflow-hidden ${farmId != null ? 'lg:left-72' : ''}`}>
        {/* Decoration at 60% under a cream wash: on a phone the 900 px copy is
            plenty even on a sharp screen, so the sizes hint asks for no more
            than that there (the true drawn width, 722 px, sent sharp phones to
            the 1800 px file as well — 150 KB for a faded backdrop). Full size
            from a laptop up. Never ahead of the screen's own content. */}
        <img onError={hideBroken} src="/photos/hills-900.webp" srcSet={photoSrcSet('/photos/hills.webp')}
          sizes={farmId != null ? '(min-width: 1024px) calc(100vw - 18rem), 400px' : '(min-width: 1024px) 100vw, 400px'}
          alt="" width={1800} height={748} fetchPriority="low" decoding="async"
          className="h-full w-full object-cover object-[center_35%] opacity-60" />
        <div className="absolute inset-0 bg-gradient-to-b from-cream/40 via-cream/60 to-cream" />
      </div>

      {/* Phone: the name of the app, and the same controls as the desktop bar. */}
      <header className="relative z-30 flex items-center justify-between gap-3 px-4 pt-[max(0.75rem,env(safe-area-inset-top))] pb-2 lg:hidden">
        <Link to="/app" className="flex min-h-[44px] min-w-0 items-center gap-2">
          <BrandMark size={34} />
          <span className="font-semibold text-leaf-deep tracking-tight">AnnRakshak</span>
        </Link>
        {controls}
      </header>

      <Toast />
      <Krishi aboveNav={farmId != null} />

      {farmId != null && (
        <aside className="hidden lg:flex fixed inset-y-0 left-0 z-30 w-72 flex-col overflow-hidden bg-[#1d4a2c] text-cream">
          <Link to="/app" className="flex items-center gap-3 px-6 pt-7 pb-8">
            <BrandMark size={44} />
            <span>
              <span className="block text-[22px] font-semibold leading-tight tracking-tight">AnnRakshak</span>
              <span className="block text-[12px] text-cream/75">{t('tagline')}</span>
            </span>
          </Link>
          <nav className="flex flex-col gap-1.5 px-4">
            {SIDE.map(({ to, icon: Icon, key }) => {
              const on = to === active
              const count = to === '/app/alerts' ? unread : 0
              const cls = `flex items-center gap-3.5 min-h-[52px] px-4 rounded-2xl text-[16px] font-medium transition-colors ${
                on ? 'bg-[#4b8b3b] text-white shadow-[0_8px_20px_-10px_rgba(0,0,0,0.5)]' : 'text-cream/90 hover:bg-white/5'}`
              const inner = (
                <>
                  <Icon className="w-5 h-5 shrink-0" strokeWidth={on ? 2.2 : 1.8} aria-hidden />
                  <span className="flex-1 text-left">{t(key)}</span>
                  {count > 0 && (
                    <span className="min-w-[22px] h-[22px] px-1.5 rounded-full bg-ember text-white text-[12px] font-semibold leading-[22px] text-center">
                      {count > 9 ? '9+' : count}
                    </span>
                  )}
                </>
              )
              return <Link key={to} to={to} data-tour={`nav-${to.split('/').pop()}`} className={cls}>{inner}</Link>
            })}
          </nav>
          <a href="tel:18001801551"
            className="relative z-10 mx-4 mt-auto mb-40 flex items-center gap-3 rounded-2xl border border-cream/20 bg-white/5 p-4 hover:bg-white/10 transition-colors">
            <Headphones className="w-7 h-7 shrink-0 text-cream" aria-hidden />
            <span className="leading-snug">
              <span className="block text-[15px] font-semibold">{t('kccName')}</span>
              <span className="block text-[15px] tabular-nums">1800-180-1551</span>
              <span className="block text-[12px] text-cream/75">{t('kccHours')}</span>
            </span>
          </a>
          {/* Ripening rice at the foot of the sidebar, rising out of its green.
              Only on a wide screen: a hidden eager <img> is still downloaded. */}
          {wide && <img aria-hidden src="/photos/panicle-closeup.webp" alt="" width={940} height={442}
            loading="lazy" decoding="async" fetchPriority="low"
            className="pointer-events-none absolute inset-x-0 bottom-0 h-48 w-full object-cover object-[30%_center] [mask-image:linear-gradient(to_top,black_45%,transparent)]" />}
        </aside>
      )}

      {/* pb clears the bottom nav (~60px), the Krishi button floating above it
          (~136px from the bottom) and the phone's gesture bar, so the last
          row of every screen can be scrolled clear of both and tapped. */}
      <main className={`relative z-10 w-full max-w-md mx-auto px-4 pb-[calc(11rem+env(safe-area-inset-bottom))] animate-fadein lg:max-w-none lg:px-10 lg:pb-28 ${
        farmId != null ? 'lg:pl-[calc(18rem+2.5rem)]' : ''}`} key={pathname}>
        <div className={`lg:mx-auto ${farmId == null || wideRoute ? 'lg:max-w-[1180px]' : 'lg:max-w-3xl'}`}>
          {/* Desktop: the greeting on the home screen, the same controls everywhere. */}
          <div className="hidden lg:flex items-start justify-between gap-6 pt-8 pb-6">
            {heading ? (
              <div>
                <h1 className="text-[32px] font-semibold leading-tight tracking-tight text-leaf-deep">{heading.title}</h1>
                <p className="mt-1 text-[16px] text-soil-dark/80">{heading.sub}</p>
              </div>
            ) : <span />}
            {controls}
          </div>
          {heading && (
            <div className="lg:hidden pt-2 pb-4">
              <h1 className="text-[26px] font-semibold leading-tight tracking-tight text-leaf-deep">{heading.title}</h1>
              <p className="mt-0.5 text-[15px] text-soil-dark/80">{heading.sub}</p>
            </div>
          )}
          {/* Picking a field comes before the screens about a field — but not
              before your own details, which belong to you and not to a plot. */}
          {farmId == null && pathname !== '/app/profile' ? <Onboard /> : <Outlet />}
        </div>
      </main>

      {farmId != null && wide && (
        <img aria-hidden src="/photos/grass.webp" alt="" loading="lazy" decoding="async" fetchPriority="low"
          className="pointer-events-none absolute bottom-0 left-72 right-0 hidden h-28 w-[calc(100%-18rem)] object-cover object-top opacity-50 lg:block [mask-image:linear-gradient(to_top,black,transparent)]" />
      )}

      {farmId != null && (
        <nav className="fixed bottom-0 inset-x-0 z-30 bg-white/95 backdrop-blur border-t border-soil-dark/10 pb-[env(safe-area-inset-bottom)] lg:hidden">
          <div className="max-w-md mx-auto grid grid-cols-5">
            {NAV.map(({ to, icon: Icon, key }) => {
              const on = lit === to
              const isScan = to === '/app/scan'
              // Unread alerts show on the tab as well as the header bell, so a
              // farmer on any screen sees that something is waiting for them.
              const count = to === '/app/alerts' ? unread : 0
              return (
                <Link
                  key={to}
                  to={to} data-tour={`nav-${to.split('/').pop()}`}
                  aria-current={active === to ? 'page' : undefined}
                  onClick={() => { if (to !== active) setTapped({ to }) }}
                  className={`relative flex min-w-0 flex-col items-center justify-center gap-1 px-0.5 py-2 min-h-[60px] text-center text-[12px] leading-tight font-medium transition-colors active:bg-soil-dark/5 [overflow-wrap:anywhere] ${
                    on ? 'text-leaf-deep font-semibold' : 'text-soil-dark/75 hover:text-soil-dark'}`}
                >
                  {count > 0 && (
                    <span className="absolute top-1 left-[calc(50%+6px)] min-w-[20px] h-[20px] px-1 rounded-full bg-ember text-cream text-[11px] font-bold leading-[20px] text-center">
                      {count > 9 ? '9+' : count}
                    </span>
                  )}
                  {isScan ? (
                    // Dark icon on ochre: cream on ochre is under 3:1 in sunlight.
                    <span className={`-mt-6 w-12 h-12 shrink-0 rounded-full flex items-center justify-center shadow-lg ring-4 ring-cream ${on ? 'bg-ochre text-soil-dark' : 'bg-leaf-deep text-cream'}`}>
                      <Icon className="w-5 h-5" aria-hidden />
                    </span>
                  ) : (
                    <span className={`flex shrink-0 items-center justify-center w-12 h-7 rounded-full transition-colors ${on ? 'bg-leaf-deep/10' : ''}`}>
                      <Icon className="w-5 h-5" strokeWidth={on ? 2.4 : 2} aria-hidden />
                    </span>
                  )}
                  {/* Two lines at most: "Alerts" in Tamil or Malayalam is one
                      word wider than the 72px a tab has at 360. */}
                  <span className="max-w-full line-clamp-2">{t(key)}</span>
                </Link>
              )
            })}
          </div>
        </nav>
      )}
    </div>
  )
}

/** A new notice or alert, the moment it is issued. */
function Toast() {
  const { toast, setToast, t } = useFarmer()
  const navigate = useNavigate()
  useEffect(() => {
    if (!toast) return
    const id = window.setTimeout(() => setToast(null), toast.severity === 'warning' ? 15000 : 8000)
    return () => window.clearTimeout(id)
  }, [toast, setToast])
  if (!toast) return null
  const warn = toast.severity === 'warning'
  return (
    <div className="fixed top-16 inset-x-0 z-40 px-3 animate-fadein">
      <div role="alert" className={`max-w-md mx-auto rounded-2xl shadow-xl p-3 flex gap-3 items-start ${warn ? 'bg-ember text-cream' : 'bg-white border border-ochre/40'}`}>
        <AlertTriangle className={`w-5 h-5 shrink-0 mt-0.5 ${warn ? '' : 'text-ochre'}`} aria-hidden />
        <button className="flex-1 text-left" onClick={() => { setToast(null); navigate(toast.url) }}>
          <span className="block text-sm font-semibold leading-snug">{toast.title}</span>
          <span className={`block text-xs mt-0.5 line-clamp-2 ${warn ? 'text-cream/85' : 'text-soil-dark/70'}`}>{toast.body}</span>
          <span className={`block text-[13px] mt-1 font-medium ${warn ? 'text-cream' : 'text-leaf-deep'}`}>{t('openLabel')} →</span>
        </button>
        <button aria-label={t('krishiClose')} onClick={() => setToast(null)}
          className={`-m-1.5 flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${warn ? 'active:bg-white/15' : 'text-soil-dark/70 active:bg-soil-dark/5'}`}>
          <X className="w-5 h-5" aria-hidden />
        </button>
      </div>
    </div>
  )
}

export default function FarmerApp() {
  return (
    <FarmerProvider>
      <TourProvider>
        <Shell />
      </TourProvider>
    </FarmerProvider>
  )
}
