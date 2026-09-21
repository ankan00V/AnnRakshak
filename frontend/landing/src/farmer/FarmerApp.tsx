import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Bell, Camera, ChevronDown, CloudSun, FlaskConical, Home as HomeIcon, MapPin, Phone, X } from 'lucide-react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { Farm, LiveEvent } from '../api/types'
import { registerWorker } from '../lib/push'
import { FarmerProvider, useFarmer } from './FarmerContext'
import LanguagePicker from './components/LanguagePicker'
import Onboard from './screens/Onboard'
import BrandMark from '../ui/BrandMark'
import AccountMenu from '../auth/AccountMenu'
import Krishi from '../krishi/Krishi'

const NAV = [
  { to: '/app', icon: HomeIcon, key: 'home' },
  { to: '/app/weather', icon: CloudSun, key: 'weatherNav' },
  { to: '/app/scan', icon: Camera, key: 'scan' },
  { to: '/app/spray', icon: FlaskConical, key: 'spray' },
  { to: '/app/alerts', icon: Bell, key: 'alerts' },
]

function Shell() {
  const { lang, setLang, farmId, setFarmId, t, unread, setUnread, setToast } = useFarmer()
  const { pathname } = useLocation()
  // Tab screens use the full desktop grid; detail screens stay at reading width.
  const wideRoute = ['/app', '/app/', '/app/weather', '/app/scan', '/app/spray', '/app/alerts'].includes(pathname)
  const navigate = useNavigate()
  const [farm, setFarm] = useState<Farm | null>(null)
  const switchFarm = () => {
    setFarmId(null)
    navigate('/app')
  }
  const synced = useRef<number | null>(null)

  useEffect(() => {
    if (farmId == null) return
    let on = true
    api.farms(lang).then((fs) => {
      if (!on) return
      const f = fs.find((x) => x.id === farmId) ?? null
      setFarm(f)
      if (!f) setFarmId(null) // stale id from an older database
      // The farmer's saved language wins when their farm opens on this device.
      if (f && synced.current !== f.id) {
        synced.current = f.id
        if (f.lang !== lang) setLang(f.lang)
      }
    }).catch(() => undefined)
    return () => {
      on = false
    }
  }, [farmId, lang, setFarmId])

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])

  useEffect(() => {
    void registerWorker()
  }, [])

  // Real-time: new weather notices and field alerts while the app is open.
  useEffect(() => {
    if (farmId == null) return
    api.notices(farmId, lang).then((n) => setUnread(n.unread)).catch(() => undefined)
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
    return () => es.close()
  }, [farmId, lang, setUnread, setToast])

  const active = pathname === '/app/result' || pathname === '/app/live'
    ? '/app/scan'
    : pathname.startsWith('/app/history')
      ? '/app'
      : NAV.slice().reverse().find((n) => pathname === n.to || pathname.startsWith(n.to + '/'))?.to ?? '/app'

  return (
    <div className="min-h-screen w-full bg-cream text-soil-dark flex flex-col">
      <header className="sticky top-0 z-30 bg-leaf-deep text-cream shadow-sm lg:shadow-none">
        <div className="max-w-md mx-auto flex items-center justify-between gap-3 px-4 py-3 lg:max-w-none lg:h-16 lg:px-6">
          {/* The field line is the switcher: a farmer with rice on one plot and
              cotton on another taps their crop to move between them. */}
          <div className="flex items-center gap-2 min-w-0">
            <Link to="/app" aria-label="AnnRakshak"><BrandMark size={34} /></Link>
            <span className="min-w-0">
              <span className="block font-semibold tracking-tight leading-none">AnnRakshak</span>
              {farm && (
                <button onClick={switchFarm} aria-label={t('switchFarm')}
                  className="flex items-center gap-1 text-[11px] text-cream/70 max-w-full">
                  <MapPin className="w-3 h-3 shrink-0" />
                  <span className="truncate">{farm.crop_name} · {farm.village || farm.district}</span>
                  <ChevronDown className="w-3 h-3 shrink-0" />
                </button>
              )}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            {farm && (
              <Link to="/app/alerts" aria-label={t('noticesTitle')}
                className="relative w-9 h-9 rounded-full bg-cream/10 flex items-center justify-center hover:bg-cream/20">
                <Bell className="w-4 h-4" />
                {unread > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-ember text-[10px] font-bold flex items-center justify-center">
                    {unread > 9 ? '9+' : unread}
                  </span>
                )}
              </Link>
            )}
            <LanguagePicker onPick={(code) => {
              setLang(code)
              if (farmId != null) api.setFarmLang(farmId, code).catch(() => undefined)
            }} />
            <AccountMenu logoutLabel={t('authLogout')} demoLabel={t('demoFarm')} />
          </div>
        </div>
      </header>

      <Toast />
      <Krishi aboveNav={farmId != null} />

      {/* Below lg this is the phone column, unchanged. On a wide screen the
          header and a dark sidebar frame the page, and every tab screen shares
          one content width and one 12-column grid (see farmer/layout.ts), so
          edges line up from screen to screen. Detail screens (a result, the
          history) keep a centred reading width. */}
      <main className={`flex-1 w-full max-w-md mx-auto px-4 pt-5 pb-28 animate-fadein lg:max-w-none lg:px-10 lg:pt-8 lg:pb-16 ${
        farmId != null ? 'lg:pl-[calc(16rem+2.5rem)]' : ''}`} key={pathname}>
        <div className={`lg:mx-auto ${farmId == null || wideRoute ? 'lg:max-w-6xl' : 'lg:max-w-3xl'}`}>
          {farmId == null ? <Onboard /> : <Outlet />}
        </div>
      </main>

      {farmId != null && (
        <nav className="fixed bottom-0 inset-x-0 z-30 bg-white/95 backdrop-blur border-t border-soil-dark/10 pb-[env(safe-area-inset-bottom)]
          lg:top-16 lg:right-auto lg:w-64 lg:border-t-0 lg:pb-0 lg:bg-leaf-deep lg:backdrop-blur-none lg:flex lg:flex-col">
          <div className="max-w-md mx-auto grid grid-cols-5 lg:max-w-none lg:w-full lg:flex lg:flex-col lg:gap-1 lg:px-4 lg:pt-4">
            {NAV.map(({ to, icon: Icon, key }) => {
              const on = active === to
              const isScan = to === '/app/scan'
              return (
                <Link
                  key={to}
                  to={to}
                  className={`flex flex-col items-center justify-center gap-0.5 py-2 min-h-[60px] text-[10.5px] font-medium transition-colors
                    lg:flex-row lg:justify-start lg:gap-3 lg:px-3 lg:min-h-[44px] lg:rounded-xl lg:text-[14px] ${
                    on ? 'text-leaf-deep lg:text-cream lg:bg-cream/10' : 'text-soil-dark/50 hover:text-soil-dark lg:text-cream/65 lg:hover:text-cream lg:hover:bg-cream/5'
                  }`}
                >
                  {isScan ? (
                    <span className={`-mt-6 w-12 h-12 rounded-full flex items-center justify-center shadow-lg ring-4 ring-cream lg:mt-0 lg:w-5 lg:h-5 lg:shadow-none lg:ring-0 lg:rounded-none lg:bg-transparent ${on ? 'bg-ochre text-cream lg:text-ochre' : 'bg-leaf-deep text-cream lg:text-inherit'}`}>
                      <Icon className="w-5 h-5" />
                    </span>
                  ) : (
                    <Icon className={`w-5 h-5 ${on ? 'lg:text-ochre' : ''}`} strokeWidth={on ? 2.4 : 2} />
                  )}
                  {t(key)}
                </Link>
              )
            })}
          </div>
          {/* Desktop only: the free helpline sits at the foot of the sidebar. */}
          <a href="tel:18001801551" className="hidden lg:flex mt-auto m-4 items-start gap-2.5 rounded-xl bg-cream/5 border border-cream/10 p-3 text-[12px] leading-snug text-cream/70 hover:text-cream hover:bg-cream/10">
            <Phone className="w-4 h-4 shrink-0 mt-0.5 text-ochre" />
            {t('callKcc')}
          </a>
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
        <AlertTriangle className={`w-5 h-5 shrink-0 mt-0.5 ${warn ? '' : 'text-ochre'}`} />
        <button className="flex-1 text-left" onClick={() => { setToast(null); navigate(toast.url) }}>
          <span className="block text-sm font-semibold leading-snug">{toast.title}</span>
          <span className={`block text-xs mt-0.5 line-clamp-2 ${warn ? 'text-cream/85' : 'text-soil-dark/70'}`}>{toast.body}</span>
          <span className={`block text-[11px] mt-1 font-medium ${warn ? 'text-cream' : 'text-leaf-deep'}`}>{t('openLabel')} →</span>
        </button>
        <button aria-label="Close" onClick={() => setToast(null)} className="shrink-0 p-1"><X className="w-4 h-4" /></button>
      </div>
    </div>
  )
}

export default function FarmerApp() {
  return (
    <FarmerProvider>
      <Shell />
    </FarmerProvider>
  )
}
