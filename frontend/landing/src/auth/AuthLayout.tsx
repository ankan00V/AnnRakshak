import { Link, Navigate, Outlet, useSearchParams } from 'react-router-dom'
import { FarmerProvider, useFarmer } from '../farmer/FarmerContext'
import LanguagePicker from '../farmer/components/LanguagePicker'
import BrandMark from '../ui/BrandMark'
import { Spinner } from '../ui/kit'
import { useAuth } from './AuthContext'
import { homeOf, safeNext } from './helpers'
import Krishi from '../krishi/Krishi'

/** Login and the two sign-ups: the brand, the language (a farmer should be
 *  able to sign up in Marathi from the first screen) and one column. */
export default function AuthLayout() {
  return (
    <FarmerProvider>
      <Frame />
    </FarmerProvider>
  )
}

function Frame() {
  const { setLang } = useFarmer()
  const { me, loading } = useAuth()
  const [params] = useSearchParams()
  if (loading) return <Spinner />
  if (me) return <Navigate to={safeNext(params.get('next')) ?? homeOf(me.role)} replace />
  return (
    <div className="min-h-screen bg-cream text-soil-dark">
      <header className="bg-leaf-deep text-cream">
        <div className="max-w-lg mx-auto flex items-center justify-between gap-3 px-4 py-3">
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
      <main className="max-w-lg mx-auto px-4 pt-6 pb-16 animate-fadein">
        <Outlet />
      </main>
    </div>
  )
}
