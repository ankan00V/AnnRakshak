import { lazy, Suspense, useCallback, useEffect, useState, type ComponentType } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { WifiOff } from 'lucide-react'
import FarmerApp from './farmer/FarmerApp'
// Already in the farmer app's own bundle (it is the field picker before a field is chosen).
import FarmerFields from './farmer/screens/Onboard'
import Home from './farmer/screens/Home'
import { AuthProvider } from './auth/AuthContext'
import RequireRole from './auth/RequireRole'
import { savedLang } from './lib/i18n'
import { PageSkeleton } from './ui/kit'

/** Shown in place of a screen whose code never reached this phone. The
 *  buttons' words are here too, not t(): the language table may be one of the
 *  files that never arrived, and English buttons under a Hindi title read as
 *  a broken screen. */
const NEEDS_SIGNAL: Record<string, { title: string; body: string; again: string; home: string }> = {
  en: { title: 'This screen needs signal the first time',
    body: 'Once it has opened with signal, it opens without signal too. Your fields and photos are safe.',
    again: 'Try again', home: 'Home' },
  hi: { title: 'इस स्क्रीन को पहली बार खोलने के लिए नेटवर्क चाहिए',
    body: 'एक बार नेटवर्क में खुल जाने के बाद यह बिना नेटवर्क के भी खुलेगी। आपके खेत और फ़ोटो सुरक्षित हैं।',
    again: 'फिर कोशिश करें', home: 'होम' },
  mr: { title: 'ही स्क्रीन पहिल्यांदा उघडण्यासाठी नेटवर्क हवे',
    body: 'एकदा नेटवर्कमध्ये उघडली की ती नेटवर्कशिवायही उघडेल. तुमची शेते आणि फोटो सुरक्षित आहेत.',
    again: 'पुन्हा प्रयत्न करा', home: 'होम' },
  bn: { title: 'এই পাতাটি প্রথমবার খুলতে নেটওয়ার্ক লাগবে',
    body: 'একবার নেটওয়ার্কে খুললে পরে নেটওয়ার্ক ছাড়াও খুলবে। আপনার জমি আর ছবি নিরাপদ আছে।',
    again: 'আবার চেষ্টা করো', home: 'হোম' },
  ta: { title: 'இந்தத் திரையை முதல் முறை திறக்க நெட்வொர்க் தேவை',
    body: 'ஒருமுறை நெட்வொர்க்கில் திறந்த பிறகு, நெட்வொர்க் இல்லாமலும் திறக்கும். உங்கள் வயல்களும் புகைப்படங்களும் பாதுகாப்பாக உள்ளன.',
    again: 'மீண்டும் முயற்சி செய்', home: 'ஹோம்' },
  te: { title: 'ఈ పేజీని మొదటిసారి తెరవడానికి నెట్‌వర్క్ కావాలి',
    body: 'ఒకసారి నెట్‌వర్క్‌తో తెరిచాక, నెట్‌వర్క్ లేకపోయినా తెరుచుకుంటుంది. మీ పొలాలు, ఫోటోలు సురక్షితంగా ఉన్నాయి.',
    again: 'మళ్ళీ ప్రయత్నించండి', home: 'హోమ్' },
  kn: { title: 'ಈ ಪುಟವನ್ನು ಮೊದಲ ಬಾರಿ ತೆರೆಯಲು ನೆಟ್‌ವರ್ಕ್ ಬೇಕು',
    body: 'ಒಮ್ಮೆ ನೆಟ್‌ವರ್ಕ್‌ನಲ್ಲಿ ತೆರೆದ ಮೇಲೆ, ನೆಟ್‌ವರ್ಕ್ ಇಲ್ಲದೆಯೂ ತೆರೆಯುತ್ತದೆ. ನಿಮ್ಮ ಹೊಲಗಳು ಮತ್ತು ಫೋಟೋಗಳು ಸುರಕ್ಷಿತವಾಗಿವೆ.',
    again: 'ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ', home: 'ಹೋಮ್' },
  ml: { title: 'ഈ പേജ് ആദ്യമായി തുറക്കാൻ നെറ്റ്‌വർക്ക് വേണം',
    body: 'ഒരിക്കൽ നെറ്റ്‌വർക്കിൽ തുറന്നാൽ പിന്നെ നെറ്റ്‌വർക്ക് ഇല്ലാതെയും തുറക്കും. നിങ്ങളുടെ വയലുകളും ഫോട്ടോകളും സുരക്ഷിതമാണ്.',
    again: 'വീണ്ടും ശ്രമിക്കുക', home: 'ഹോം' },
  gu: { title: 'આ પાનું પહેલી વાર ખોલવા નેટવર્ક જોઈએ',
    body: 'એક વાર નેટવર્કમાં ખુલ્યા પછી તે નેટવર્ક વિના પણ ખુલશે. તમારાં ખેતરો અને ફોટા સુરક્ષિત છે.',
    again: 'ફરી પ્રયાસ કરો', home: 'હોમ' },
  pa: { title: 'ਇਹ ਪੰਨਾ ਪਹਿਲੀ ਵਾਰ ਖੋਲ੍ਹਣ ਲਈ ਨੈੱਟਵਰਕ ਚਾਹੀਦਾ ਹੈ',
    body: 'ਇੱਕ ਵਾਰ ਨੈੱਟਵਰਕ ਨਾਲ ਖੁੱਲ੍ਹਣ ਤੋਂ ਬਾਅਦ ਇਹ ਬਿਨਾਂ ਨੈੱਟਵਰਕ ਵੀ ਖੁੱਲ੍ਹੇਗਾ। ਤੁਹਾਡੇ ਖੇਤ ਅਤੇ ਫ਼ੋਟੋਆਂ ਸੁਰੱਖਿਅਤ ਹਨ।',
    again: 'ਦੁਬਾਰਾ ਕੋਸ਼ਿਸ਼ ਕਰੋ', home: 'ਹੋਮ' },
  od: { title: 'ଏହି ପୃଷ୍ଠା ପ୍ରଥମ ଥର ଖୋଲିବାକୁ ନେଟୱର୍କ ଦରକାର',
    body: 'ଥରେ ନେଟୱର୍କରେ ଖୋଲିଗଲା ପରେ ଏହା ନେଟୱର୍କ ବିନା ମଧ୍ୟ ଖୋଲିବ। ଆପଣଙ୍କ ଜମି ଓ ଫଟୋ ସୁରକ୍ଷିତ ଅଛି।',
    again: 'ପୁଣିଥରେ ଚେଷ୍ଟା କରନ୍ତୁ', home: 'ଘର' },
}

/** Where "Home" goes from a screen that could not open: the console's own
 *  front page for an officer, the farmer's for a farmer, else the front page. */
function homeFor(path: string): string {
  if (path === '/officer' || path.startsWith('/officer/')) return '/officer'
  if (path === '/app' || path.startsWith('/app/')) return '/app'
  return '/'
}

/** Outside FarmerProvider on purpose: this can stand in for any screen,
 *  the sign-in forms and the officer console included. */
function NeedsSignal({ onRetry, busy }: { onRetry: () => void; busy: boolean }) {
  const s = NEEDS_SIGNAL[savedLang()] ?? NEEDS_SIGNAL.en
  return (
    <div role="alert" className="min-h-[60vh] flex items-center justify-center px-4 py-10">
      <div className="max-w-sm w-full rounded-[28px] bg-white p-6 text-center shadow-[0_10px_30px_-18px_rgba(43,29,18,0.35)] ring-1 ring-soil-dark/[0.06]">
        <WifiOff className="w-9 h-9 text-ochre mx-auto" aria-hidden />
        <p className="mt-3 text-[17px] font-semibold text-soil-dark">{s.title}</p>
        <p className="mt-2 text-[14px] leading-relaxed text-soil-dark/75">{s.body}</p>
        <button onClick={onRetry} disabled={busy} aria-busy={busy}
          className="mt-5 w-full min-h-[48px] rounded-full bg-leaf-deep text-cream text-[15px] font-semibold disabled:opacity-60">
          {s.again}
        </button>
        <a href={homeFor(window.location.pathname)} className="mt-2 flex items-center justify-center w-full min-h-[44px] rounded-full text-[14px] font-medium text-leaf-deep">
          {s.home}
        </a>
      </div>
    </div>
  )
}

const RELOADED = 'ar.chunk-reload'
const breath = () => new Promise((r) => setTimeout(r, 1200))

/** lazy(), for a phone on a bad line. A chunk that fails is tried once more
 *  after a breath (2G drops a request and serves the next). If it still
 *  fails while the phone believes it is online, the likeliest cause is a new
 *  deploy that removed the old file names: reload once to pick up the new
 *  page. Offline, or after that reload, the screen says it needs signal in the
 *  farmer's language, instead of the app's English crash page.
 *
 *  lazy() keeps whatever its factory resolved to for good, so a failure must
 *  not resolve to NeedsSignal itself: the screen would stay "needs signal" after
 *  the signal came back, until a full reload. It resolves to Retrying, which
 *  asks for the chunk again when it is shown, when the phone goes back online
 *  and on Try again, and draws the real screen once it arrives. */
function route<T extends ComponentType<object>>(load: () => Promise<{ default: T }>) {
  let real: T | null = null
  let failedAt = 0
  // One request at a time: 'online' and a tap can land together on a phone
  // whose link just came back, and 2G has no room for the same chunk twice.
  let inflight: Promise<{ default: T }> | null = null
  const fetchScreen = () => inflight ??= load()
    .then((m) => { real = m.default; return m })
    .finally(() => { inflight = null })

  function Retrying(props: object) {
    const [, arrived] = useState(0)
    const [busy, setBusy] = useState(false)
    const retry = useCallback(() => {
      if (real) return
      setBusy(true)
      fetchScreen()
        .then(() => arrived((n) => n + 1))
        .catch(() => { failedAt = Date.now() })
        .finally(() => setBusy(false))
    }, [])
    useEffect(() => {
      if (real) return
      // Not straight after the failure that put this here: that was two tries
      // already. Coming back to the screen later is the farmer asking again.
      if (Date.now() - failedAt > 3000) retry()
      window.addEventListener('online', retry)
      return () => window.removeEventListener('online', retry)
    }, [retry])
    const Screen = real as ComponentType<object> | null
    return Screen ? <Screen {...props} /> : <NeedsSignal onRetry={retry} busy={busy} />
  }

  return lazy(() =>
    fetchScreen()
      .catch(() => breath().then(fetchScreen))
      .catch((): { default: T } => {
        failedAt = Date.now()
        let reloaded = true
        try {
          reloaded = Date.now() - Number(sessionStorage.getItem(RELOADED) ?? 0) < 30_000
          if (navigator.onLine && !reloaded) sessionStorage.setItem(RELOADED, String(Date.now()))
        } catch { /* storage blocked: never loop on reloads */ }
        if (navigator.onLine && !reloaded) window.location.reload()
        return { default: Retrying as unknown as T }
      }),
  )
}

// Farmers load only their own screens on slow rural networks; the expert
// console, the Leaflet-heavy officials' dashboard and the sign-up forms are
// separate chunks. So is the public front page: its brand illustrations are
// ~90 KB of inline images a farmer opening /app never sees.
const Landing = route(() => import('./Landing'))
const Scan = route(() => import('./farmer/screens/Scan'))
const Live = route(() => import('./farmer/screens/Live'))
const Weather = route(() => import('./farmer/screens/Weather'))
const Result = route(() => import('./farmer/screens/Result'))
const Spray = route(() => import('./farmer/screens/Spray'))
const Alerts = route(() => import('./farmer/screens/Alerts'))
const FarmerProfile = route(() => import('./farmer/screens/Profile'))
const History = route(() => import('./farmer/screens/History'))
const ProblemDetail = route(() => import('./farmer/screens/History').then((m) => ({ default: m.ProblemDetail })))
const OfficerShell = route(() => import('./officer/OfficerShell'))
const OfficerToday = route(() => import('./officer/pages/Today'))
const OfficerQueue = route(() => import('./officer/pages/Queue'))
const OfficerFarm = route(() => import('./officer/pages/FarmPage'))
const OfficerMap = route(() => import('./officer/pages/MapPage'))
const OfficerAdvisories = route(() => import('./officer/pages/Advisories'))
const OfficerInputs = route(() => import('./officer/pages/Inputs'))
const OfficerModel = route(() => import('./officer/pages/ModelGaps'))
const OfficerProfile = route(() => import('./officer/pages/Profile'))
const OfficerOfficers = route(() => import('./officer/pages/Officers'))
const AuthLayout = route(() => import('./auth/AuthLayout'))
const Login = route(() => import('./auth/Login'))
const SignupChoose = route(() => import('./auth/SignupChoose'))
const SignupFarmer = route(() => import('./auth/SignupFarmer'))
const SignupExpert = route(() => import('./auth/SignupExpert'))

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Suspense fallback={<PageSkeleton />}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route element={<AuthLayout />}>
              <Route path="/login" element={<Login />} />
              <Route path="/signup" element={<SignupChoose />} />
              <Route path="/signup/farmer" element={<SignupFarmer />} />
              <Route path="/signup/expert" element={<SignupExpert />} />
            </Route>
            <Route path="/app" element={<RequireRole role="farmer"><FarmerApp /></RequireRole>}>
              <Route index element={<Home />} />
              <Route path="scan" element={<Scan />} />
              <Route path="live" element={<Live />} />
              <Route path="weather" element={<Weather />} />
              <Route path="result" element={<Result />} />
              <Route path="spray" element={<Spray />} />
              <Route path="alerts" element={<Alerts />} />
              <Route path="history" element={<History />} />
              <Route path="history/:id" element={<ProblemDetail />} />
              <Route path="profile" element={<FarmerProfile />} />
              <Route path="fields" element={<FarmerFields />} />
            </Route>
            {/* One queue, not two: the district office's is the better of the pair. */}
            <Route path="/expert" element={<Navigate to="/officer/queue" replace />} />
            <Route path="/officer" element={<RequireRole role="expert"><OfficerShell /></RequireRole>}>
              <Route index element={<OfficerToday />} />
              <Route path="queue" element={<OfficerQueue />} />
              <Route path="farm/:id" element={<OfficerFarm />} />
              <Route path="map" element={<OfficerMap />} />
              <Route path="advisories" element={<OfficerAdvisories />} />
              <Route path="inputs" element={<OfficerInputs />} />
              <Route path="model" element={<OfficerModel />} />
              <Route path="officers" element={<OfficerOfficers />} />
              <Route path="profile" element={<OfficerProfile />} />
              {/* A console tab that has been taken away should land on the
                  console, not on the public page. */}
              <Route path="*" element={<Navigate to="/officer" replace />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </AuthProvider>
    </BrowserRouter>
  )
}
