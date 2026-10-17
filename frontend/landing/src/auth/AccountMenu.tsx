import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Download, Headphones, LogOut, ShieldCheck, Trash2 } from 'lucide-react'
import { api } from '../api/client'
import { useAuth } from './AuthContext'

/** Labels for the two things the law gives a farmer over their own data.
 *  Absent, the section is not shown — an officer's account is a different
 *  matter: their cases are a record the district keeps. */
export type PrivacyLabels = {
  yourData: string; downloadData: string; deleteAccount: string; deleteWhat: string
  typeToConfirm: string; confirmWord: string; forever: string; cancel: string; done: string
}

/** The signed-in person in a dark header: initials, and a menu with who they
 *  are, what they may do with their own data, and Log out. Labels default to
 *  English (the expert screens). */
export default function AccountMenu({ logoutLabel = 'Log out', demoLabel = 'Demo', extra, privacy }: {
  logoutLabel?: string; demoLabel?: string
  /** One more item above Log out (the farmer app's "App tour"). */
  extra?: { label: string; onClick: () => void }
  privacy?: PrivacyLabels
}) {
  const { me, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [erasing, setErasing] = useState(false)
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [erased, setErased] = useState(false)
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
          {privacy && !me.is_demo && (
            <div className="mt-4 pt-3 border-t border-soil-dark/10">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-soil-dark/45">{privacy.yourData}</p>
              <a href={api.myDataUrl} download
                className="mt-2 flex items-center gap-2 text-sm text-leaf-deep font-medium hover:underline">
                <Download className="w-4 h-4" />
                {privacy.downloadData}
              </a>
              {!erasing ? (
                <button onClick={() => setErasing(true)}
                  className="mt-2 flex items-center gap-2 text-sm text-ember font-medium hover:underline">
                  <Trash2 className="w-4 h-4" />
                  {privacy.deleteAccount}
                </button>
              ) : (
                <div className="mt-2 rounded-xl bg-ember/5 border border-ember/20 p-3">
                  <p className="text-[12px] leading-snug text-soil-dark/80">{privacy.deleteWhat}</p>
                  <label className="mt-2 block text-[11px] text-soil-dark/60">{privacy.typeToConfirm}</label>
                  <input value={typed} onChange={(e) => setTyped(e.target.value)} autoFocus
                    aria-label={privacy.typeToConfirm}
                    className="mt-1 w-full min-h-[40px] rounded-lg border border-soil-dark/20 bg-white px-3 text-sm" />
                  {erased ? (
                    // Said here rather than in an alert box: the last thing this
                    // account sees should still look like the app.
                    <p className="mt-3 text-sm font-medium text-leaf-deep">{privacy.done}</p>
                  ) : (
                    <>
                      <button
                        disabled={busy || typed.trim().toUpperCase() !== privacy.confirmWord}
                        onClick={async () => {
                          setBusy(true)
                          try {
                            await api.eraseAccount(typed.trim().toUpperCase())
                            setErased(true)
                            // A moment to read it, then out — there is no
                            // account to come back to.
                            setTimeout(() => window.location.replace('/'), 1800)
                          } finally {
                            setBusy(false)
                          }
                        }}
                        className="mt-2 w-full min-h-[40px] rounded-full bg-ember text-cream text-sm font-semibold disabled:opacity-40">
                        {privacy.forever}
                      </button>
                      <button onClick={() => { setErasing(false); setTyped('') }}
                        className="mt-1.5 w-full min-h-[36px] text-sm text-soil-dark/70">
                        {privacy.cancel}
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
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
