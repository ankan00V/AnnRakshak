import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Headphones, LogOut, ShieldCheck } from 'lucide-react'
import { useAuth } from './AuthContext'

/** The signed-in person in a dark header: initials, and a menu with who they
 *  are and Log out. Labels default to English (the expert screens). */
export default function AccountMenu({ logoutLabel = 'Log out', demoLabel = 'Demo', extra }: {
  logoutLabel?: string; demoLabel?: string
  /** One more item above Log out (the farmer app's "App tour"). */
  extra?: { label: string; onClick: () => void }
}) {
  const { me, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  if (!me) return null
  const initials = me.name.split(/\s+/)
    .filter((w) => /\p{L}/u.test(w[0] ?? '') && !/^(dr|prof|shri|smt|mr|mrs|ms|km)\.?$/i.test(w))
    .slice(0, 2).map((w) => w[0]).join('').toUpperCase()
  const org = me.profile?.designation_name ? `${me.profile.designation_name} · ${me.profile.organisation}` : null
  const place = me.profile?.village ? [me.profile.village, me.profile.district].filter(Boolean).join(', ') : null

  return (
    <div className="relative" ref={box}>
      <button onClick={() => setOpen((o) => !o)} aria-label={me.name} aria-expanded={open}
        className="w-9 h-9 rounded-full bg-ochre text-soil-dark text-[13px] font-bold flex items-center justify-center ring-2 ring-cream/20 hover:ring-cream/40">
        {initials || '•'}
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-72 rounded-2xl bg-white text-soil-dark shadow-xl border border-soil-dark/10 p-4 z-50 animate-fadein">
          <p className="font-semibold leading-tight">{me.name}</p>
          {org && <p className="mt-0.5 text-[12px] text-soil-dark/60 leading-snug">{org}</p>}
          {place && <p className="mt-0.5 text-[12px] text-soil-dark/60">{place}</p>}
          <p className="mt-2 text-[12px] text-soil-dark/50 break-all">{[me.phone, me.email].filter(Boolean).join(' · ')}</p>
          <div className="mt-2 flex gap-1.5 flex-wrap">
            {me.is_demo && <span className="px-2 py-0.5 rounded-full bg-ochre/15 text-[#8a5a17] text-[11px] font-medium">{demoLabel}</span>}
            {me.profile?.verified && (
              <span className="px-2 py-0.5 rounded-full bg-leaf/15 text-leaf-deep text-[11px] font-medium inline-flex items-center gap-1">
                <ShieldCheck className="w-3 h-3" />Verified
              </span>
            )}
          </div>
          {extra && (
            <button onClick={() => { setOpen(false); extra.onClick() }}
              className="mt-4 w-full min-h-[42px] rounded-full bg-leaf-deep text-cream text-sm font-medium flex items-center justify-center gap-2 hover:brightness-110">
              <Headphones className="w-4 h-4" />
              {extra.label}
            </button>
          )}
          <button onClick={() => { navigate('/', { replace: true }); void logout() }}
            className={`${extra ? 'mt-2' : 'mt-4'} w-full min-h-[42px] rounded-full border border-soil-dark/15 text-sm font-medium flex items-center justify-center gap-2 hover:bg-cream`}>
            <LogOut className="w-4 h-4" />
            {logoutLabel}
          </button>
        </div>
      )}
    </div>
  )
}
