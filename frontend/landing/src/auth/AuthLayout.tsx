import { Check, Sprout, UserCheck } from 'lucide-react'
import { Link, Navigate, Outlet, useLocation, useSearchParams } from 'react-router-dom'
import { FarmerProvider, useFarmer } from '../farmer/FarmerContext'
import LanguagePicker from '../farmer/components/LanguagePicker'
import BrandMark from '../ui/BrandMark'
import { PageSkeleton } from '../ui/kit'
import { useAuth } from './AuthContext'
import { homeOf, safeNext } from './helpers'
import { ProgressProvider, useProgress } from './progress'
import Krishi from '../krishi/Krishi'

/** Login and the two sign-ups: the brand, the language (a farmer should be
 *  able to sign up in Marathi from the first screen) and one column.
 *
 *  One column is right on the phone the farmer actually holds. On a laptop it
 *  left a 400 px ribbon adrift in a 1500 px window, so from `lg` up the screen
 *  splits: the panel on the left says where you are and how far there is to go,
 *  and the form keeps the right half at a readable width. Nothing below `lg`
 *  changes. */
export default function AuthLayout() {
  return (
    <FarmerProvider>
      <ProgressProvider>
        <Frame />
      </ProgressProvider>
    </FarmerProvider>
  )
}

function Frame() {
  const { setLang } = useFarmer()
  const { me, loading } = useAuth()
  const [params] = useSearchParams()
  if (loading) return <PageSkeleton />
  if (me) return <Navigate to={safeNext(params.get('next')) ?? homeOf(me.role)} replace />
  return (
    <div className="min-h-screen bg-cream text-soil-dark">
      <header className="bg-leaf-deep text-cream">
        <div className="max-w-lg lg:max-w-none lg:w-full mx-auto flex items-center justify-between gap-3 px-4 lg:px-8 py-3">
          <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight">
            <BrandMark size={34} />
            AnnRakshak
          </Link>
          <div className="flex items-center gap-2">
            <Krishi anchor="header" />
            <LanguagePicker onPick={setLang} />
          </div>
        </div>
      </header>
      <div className="lg:grid lg:grid-cols-[minmax(20rem,30%)_1fr] lg:items-stretch">
        <Aside />
        {/* A short step (the login box, the fork) would otherwise sit against
            the top of a laptop screen with half a window of cream under it. */}
        <div className="lg:min-h-[calc(100vh-58px)] lg:flex lg:flex-col lg:justify-center">
          <main className="w-full max-w-lg lg:max-w-2xl mx-auto px-4 lg:px-10 pt-6 pb-16 lg:py-12 animate-fadein">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  )
}

/** The left half on a laptop: what this screen is for, and — on a sign-up —
 *  the whole walk with the current step lit. Every line here is a string the
 *  form already uses, so the panel speaks all eleven languages for free. */
function Aside() {
  const { t } = useFarmer()
  const { pathname } = useLocation()
  const progress = useProgress()

  const copy = pathname.startsWith('/signup/farmer')
    ? { title: t('authFarmerCard'), sub: t('authFarmerCardSub') }
    : pathname.startsWith('/signup/expert')
      ? { title: t('authExpertCard'), sub: t('authExpertCardSub') }
      : pathname.startsWith('/signup')
        ? { title: t('authWhoAreYou'), sub: t('authWhoSub') }
        : { title: t('authLoginTitle'), sub: t('authLoginSub') }

  return (
    <aside className="hidden lg:flex flex-col gap-10 bg-leaf-deep text-cream px-10 py-12 sticky top-0 self-start h-[calc(100vh-58px)] overflow-y-auto">
      <div>
        <h2 className="font-instrument-serif text-[34px] leading-tight">{copy.title}</h2>
        <p className="mt-2.5 text-[14px] leading-relaxed text-cream/70">{copy.sub}</p>
      </div>

      {/* On the fork itself the two cards say this already; saying it twice on
          one screen is noise. */}
      {progress ? <Walk {...progress} /> : pathname.startsWith('/login') ? <Audiences /> : null}

      <p className="mt-auto text-[12px] leading-relaxed text-cream/45">{t('authEmailNote')}</p>
    </aside>
  )
}

/** The steps of this sign-up, done, open and still to come. */
function Walk({ step, titles }: { step: number; titles: string[] }) {
  const { t } = useFarmer()
  return (
    <ol className="space-y-0">
      {titles.map((title, i) => {
        const done = i < step
        const here = i === step
        return (
          <li key={title + i} className="flex gap-3.5">
            <span className="flex flex-col items-center">
              <span className={`w-7 h-7 shrink-0 rounded-full border flex items-center justify-center text-[12px] font-semibold ${
                done ? 'bg-cream/90 border-cream/90 text-leaf-deep'
                  : here ? 'border-cream text-cream' : 'border-cream/25 text-cream/40'}`}>
                {done ? <Check className="w-3.5 h-3.5" /> : i + 1}
              </span>
              {i < titles.length - 1 && (
                <span className={`w-px flex-1 my-1 ${i < step ? 'bg-cream/70' : 'bg-cream/15'}`} />
              )}
            </span>
            <span className={`pb-5 text-[14px] leading-tight ${
              here ? 'font-semibold text-cream' : done ? 'text-cream/65' : 'text-cream/40'}`}>
              {title}
              {here && (
                <span className="block mt-1 text-[11px] font-normal uppercase tracking-wider text-cream/45">
                  {t('authStep').replace('{n}', String(step + 1)).replace('{total}', String(titles.length))}
                </span>
              )}
            </span>
          </li>
        )
      })}
    </ol>
  )
}

/** On login and on the fork, where there is no walk to draw: who the two apps
 *  are for, so somebody landing on the login screen can tell which one is theirs. */
function Audiences() {
  const { t } = useFarmer()
  const rows = [
    { icon: Sprout, title: t('authFarmerCard'), sub: t('authFarmerCardSub') },
    { icon: UserCheck, title: t('authExpertCard'), sub: t('authExpertCardSub') },
  ]
  return (
    <ul className="space-y-5">
      {rows.map(({ icon: Icon, title, sub }) => (
        <li key={title} className="flex gap-3.5">
          <span className="w-9 h-9 shrink-0 rounded-xl bg-cream/10 flex items-center justify-center">
            <Icon className="w-[18px] h-[18px]" />
          </span>
          <span>
            <span className="block text-[14px] font-semibold">{title}</span>
            <span className="block mt-1 text-[13px] leading-relaxed text-cream/60">{sub}</span>
          </span>
        </li>
      ))}
    </ul>
  )
}
