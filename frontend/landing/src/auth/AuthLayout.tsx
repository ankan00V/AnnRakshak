import { Link, Navigate, Outlet, useLocation, useSearchParams } from 'react-router-dom'
import { FarmerProvider, useFarmer } from '../farmer/FarmerContext'
import LanguagePicker from '../farmer/components/LanguagePicker'
import BrandMark from '../ui/BrandMark'
import { PageSkeleton } from '../ui/kit'
import { useAuth } from './AuthContext'
import { homeOf, safeNext } from './helpers'
import { ProgressProvider, useDraft, type Draft } from './progress'
import { Handset, ProfilePreview } from './Preview'
import Krishi from '../krishi/Krishi'

/** Login and the two sign-ups: one calm card over the field. On a sign-up a
 *  phone stands beside it, showing the profile the farmer or expert is making
 *  as it fills in; login and the fork are the card alone.
 *
 *  The brand and the language sit over the photograph on every screen: a
 *  farmer should be able to sign up in Marathi from the first screen. On a
 *  phone the card is the page, over the same photograph; the preview phone is
 *  for screens with room beside the form. */
export default function AuthLayout() {
  return (
    <FarmerProvider>
      <ProgressProvider>
        <Frame />
      </ProgressProvider>
    </FarmerProvider>
  )
}

/** What this screen is for, in the strings the forms already use, so it
 *  speaks all eleven languages. */
function useCopy() {
  const { t } = useFarmer()
  const { pathname } = useLocation()
  return pathname.startsWith('/signup/farmer')
    ? { title: t('authFarmerCard'), sub: t('authFarmerCardSub') }
    : pathname.startsWith('/signup/expert')
      ? { title: t('authExpertCard'), sub: t('authExpertCardSub') }
      : pathname.startsWith('/signup')
        ? { title: t('authWhoAreYou'), sub: t('authWhoSub') }
        : { title: t('authLoginTitle'), sub: t('authLoginSub') }
}

function Frame() {
  const { setLang, t } = useFarmer()
  const { me, loading } = useAuth()
  const [params] = useSearchParams()
  const { pathname } = useLocation()
  const copy = useCopy()
  const draft = useDraft()
  if (loading) return <PageSkeleton />
  // A signed-in person has no business on the sign-up forms — except the one
  // trying out the shared demonstration account, who reached here by pressing
  // "add your own field". Sending them back to the demo is the one answer that
  // cannot be what they meant. Letting them look costs nothing: signing up
  // replaces the session, and backing out leaves the demo as it was.
  //
  // The sign-in page is not one of those forms. "Demo farmer" signs you in
  // right here, so a demo session that is not sent on has nowhere to go and
  // the button looks broken.
  if (me && (!me.is_demo || pathname.startsWith('/login'))) {
    return <Navigate to={safeNext(params.get('next')) ?? homeOf(me.role)} replace />
  }
  return (
    <div className="relative min-h-screen bg-[#10301b] text-soil-dark">
      {/* The field, held still behind everything, softened so the card is
          the thing you look at. */}
      <div aria-hidden className="fixed inset-0 overflow-hidden">
        <img src="/photos/impact-tree.webp" alt="" decoding="async"
          className="h-full w-full scale-105 object-cover object-[70%_55%] blur-[2px]" />
        <div className="absolute inset-0 bg-[#0e2a17]/45" />
        <div className="absolute inset-0 bg-gradient-to-b from-black/35 via-transparent to-[#0e2a17]/60" />
      </div>

      <header className="relative z-20 flex items-center justify-between gap-3 px-4 py-3 text-cream md:px-8 md:py-5">
        <Link to="/" className="inline-flex items-center gap-2.5">
          <span className="rounded-full bg-white p-[3px] shadow-sm"><BrandMark size={34} /></span>
          <span className="leading-tight">
            <span className="block text-[17px] font-semibold tracking-tight">AnnRakshak</span>
            <span className="hidden text-[11px] text-cream/75 sm:block">{t('landTagline')}</span>
          </span>
        </Link>
        <div className="flex items-center gap-2">
          <Krishi anchor="header" />
          <LanguagePicker onPick={setLang} />
        </div>
      </header>

      <div className="relative z-10 mx-auto flex max-w-[1080px] items-start justify-center gap-14 px-3 pb-16 pt-2 md:px-8 lg:pt-8 xl:gap-20">
        <main className={`w-full ${draft ? 'max-w-[580px]' : pathname.startsWith('/login') ? 'max-w-[480px]' : 'max-w-[620px]'} animate-fadein rounded-[28px] bg-white px-5 py-7 shadow-[0_40px_90px_-40px_rgba(0,0,0,0.65)] ring-1 ring-black/5 sm:px-9 sm:py-9`}>
          <h1 className="font-display text-[30px] leading-[1.08] tracking-[-0.01em] text-[#1f3a26] sm:text-[34px]">{copy.title}</h1>
          <p className="mt-2 text-[15px] leading-relaxed text-soil-dark/70">{copy.sub}</p>
          <div className="mt-7">
            <Outlet />
          </div>
        </main>
        {draft && <Beside draft={draft} />}
      </div>
    </div>
  )
}

/** The phone beside a sign-up: the profile being made, held in view while a
 *  long form scrolls. */
function Beside({ draft }: { draft: Draft }) {
  return (
    <div className="sticky top-8 hidden shrink-0 lg:block">
      <Handset><ProfilePreview draft={draft} /></Handset>
    </div>
  )
}
