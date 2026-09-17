import type { ReactNode } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { ShieldAlert } from 'lucide-react'
import type { Role } from '../api/types'
import { FarmerProvider, useFarmer } from '../farmer/FarmerContext'
import BrandMark from '../ui/BrandMark'
import { Card, Spinner } from '../ui/kit'
import { useAuth } from './AuthContext'
import { homeOf } from './helpers'

/** The farmer app is for farmers; the expert console and the officials'
 *  dashboard are for experts. The server enforces the same rule on every
 *  call — this only keeps people out of screens that would fail. */
export default function RequireRole({ role, children }: { role: Role; children: ReactNode }) {
  const { me, loading } = useAuth()
  const { pathname, search } = useLocation()
  if (loading) return <div className="min-h-screen bg-cream"><Spinner /></div>
  if (!me) return <Navigate to={`/login?role=${role}&next=${encodeURIComponent(pathname + search)}`} replace />
  if (me.role !== role) {
    return (
      <FarmerProvider>
        <WrongRole want={role} />
      </FarmerProvider>
    )
  }
  return children
}

function WrongRole({ want }: { want: Role }) {
  const { t } = useFarmer()
  const { me, logout } = useAuth()
  const navigate = useNavigate()
  const roleName = (r: Role) => t(r === 'farmer' ? 'authFarmer' : 'authExpert')
  return (
    <div className="min-h-screen bg-cream text-soil-dark flex flex-col items-center justify-center px-4">
      <Link to="/" className="flex items-center gap-2 font-semibold mb-6"><BrandMark size={34} />AnnRakshak</Link>
      <Card className="max-w-sm w-full p-6 text-center space-y-4">
        <ShieldAlert className="w-10 h-10 text-ochre mx-auto" />
        <div>
          <p className="font-semibold">{t('authWrongRole').replace('{role}', roleName(want))}</p>
          <p className="mt-1 text-sm text-soil-dark/60">
            {t('authWrongRoleSub').replace('{name}', `${me!.name} · ${roleName(me!.role)}`)}
          </p>
        </div>
        <Link to={homeOf(me!.role)} className="block w-full min-h-[48px] leading-[48px] rounded-full bg-leaf-deep text-cream text-sm font-semibold">
          {t('authGoHome')}
        </Link>
        <button onClick={async () => { await logout(); navigate(`/login?role=${want}`) }}
          className="w-full min-h-[44px] rounded-full border border-soil-dark/15 text-sm font-medium">
          {t('authSwitch')}
        </button>
      </Card>
    </div>
  )
}
