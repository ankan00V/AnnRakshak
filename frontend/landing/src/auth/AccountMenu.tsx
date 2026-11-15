import { useEffect, useId, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Download, Headphones, LogOut, ShieldCheck, Trash2, UserRound } from 'lucide-react'
import { api } from '../api/client'
import { useAuth } from './AuthContext'

/** Labels for the two things the law gives a farmer over their own data.
 *  Absent, the section is not shown — an officer's account is a different
 *  matter: their cases are a record the district keeps. */
export type PrivacyLabels = {
  yourData: string; downloadData: string; deleteAccount: string; deleteWhat: string
  typeToConfirm: string; confirmWord: string; forever: string; cancel: string; done: string
  /** The notice: what is kept, where, and who can see it. The DPDP Act asks
   *  for this to be told plainly rather than buried, and it belongs beside the
   *  two buttons that act on it. */
  what: string; phone: string; cookie: string; noAds: string; server: string
}

/** "Verified" in the page's language. AccountMenu is shared with the expert
 *  screens and has no farmer context, so it reads <html lang>, which the
 *  farmer app keeps on the farmer's language. A `verifiedLabel` prop wins. */
const VERIFIED: Record<string, string> = {
  en: 'Verified', hi: 'सत्यापित', mr: 'पडताळलेले', bn: 'যাচাই করা', ta: 'சரிபார்க்கப்பட்டது',
  te: 'ధృవీకరించబడింది', kn: 'ಪರಿಶೀಲಿಸಲಾಗಿದೆ', ml: 'പരിശോധിച്ചു', gu: 'ચકાસાયેલ', pa: 'ਪ੍ਰਮਾਣਿਤ', od: 'ଯାଞ୍ଚ ହୋଇଛି',
}
const verifiedText = () => {
  const code = (document.documentElement.lang || 'en').slice(0, 2).toLowerCase()
  // BCP 47 calls Odia "or"; the app's own code for it is "od".
  return VERIFIED[code === 'or' ? 'od' : code] ?? VERIFIED.en
}

/** The signed-in person in a dark header: initials, and a menu with who they
 *  are, what they may do with their own data, and Log out. Labels default to
 *  English (the expert screens). */
export default function AccountMenu({ logoutLabel = 'Log out', demoLabel = 'Demo', verifiedLabel, extra, privacy, profile, light = false }: {
  logoutLabel?: string; demoLabel?: string; verifiedLabel?: string
  /** Where this role's own record lives, and what to call it. */
  profile?: { to: string; label: string }
  /** One more item above Log out (the farmer app's "App tour"). */
  extra?: { label: string; onClick: () => void }
  privacy?: PrivacyLabels
  /** On a light top bar: a dark avatar instead of an ochre one. */
  light?: boolean
}) {
  const { me, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [erasing, setErasing] = useState(false)
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [erased, setErased] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  // A show-and-hide panel, not a menu: no role=menu items or arrow keys,
  // so it says it is expanded and which panel it opens, nothing more.
  const panelId = useId()

  // pointerdown rather than mousedown: one listener for a finger and a mouse.
  // Escape closes too, and hands focus back to the avatar it came from.
  useEffect(() => {
    if (!open) return
    const close = (e: PointerEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false)
    }
    const esc = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      setOpen(false)
      trigger.current?.focus()
    }
    document.addEventListener('pointerdown', close)
    window.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('pointerdown', close)
      window.removeEventListener('keydown', esc)
    }
  }, [open])

  if (!me) return null
  const initials = me.name.split(/\s+/)
    .filter((w) => /\p{L}/u.test(w[0] ?? '') && !/^(dr|prof|shri|smt|mr|mrs|ms|km)\.?$/i.test(w))
    .slice(0, 2).map((w) => w[0]).join('').toUpperCase()
  const org = me.profile?.designation_name ? `${me.profile.designation_name} · ${me.profile.organisation}` : null
  const place = me.profile?.village ? [me.profile.village, me.profile.district].filter(Boolean).join(', ') : null

  return (
    <div className="relative" ref={box}>
      {/* The dark header's avatar stays 36px to look at, but sits in a 44px
          button (pulled in by -m-1 so the header does not grow): a 36px
          target is one a thumb misses. */}
      <button ref={trigger} onClick={() => setOpen((o) => !o)} aria-label={me.name}
        aria-expanded={open} aria-controls={panelId}
        className={light
          ? 'w-11 h-11 rounded-full bg-leaf-deep text-cream text-[13px] font-semibold flex items-center justify-center ring-2 ring-white hover:brightness-110'
          : 'group -m-1 w-11 h-11 rounded-full flex items-center justify-center'}>
        {light ? (initials || '•') : (
          <span className="w-9 h-9 rounded-full bg-ochre text-soil-dark text-[13px] font-bold flex items-center justify-center ring-2 ring-cream/20 group-hover:ring-cream/40">
            {initials || '•'}
          </span>
        )}
      </button>
      {/* Capped to the screen and scrolled inside: opened with the data notice
          and the delete confirmation on a short phone, it ran off the bottom
          with Log out out of reach. */}
      {open && (
        <div id={panelId} className="absolute right-0 mt-2 w-72 max-w-[calc(100vw-2rem)] max-h-[calc(100dvh-5rem)] overflow-y-auto overscroll-contain rounded-2xl bg-white text-soil-dark shadow-xl border border-soil-dark/10 p-4 z-50 animate-fadein">
          <p className="font-semibold leading-tight">{me.name}</p>
          {org && <p className="mt-0.5 text-[13px] text-soil-dark/70 leading-snug">{org}</p>}
          {place && <p className="mt-0.5 text-[13px] text-soil-dark/70">{place}</p>}
          <p className="mt-2 text-[13px] text-soil-dark/70 break-all">{[me.phone, me.email].filter(Boolean).join(' · ')}</p>
          <div className="mt-2 flex gap-1.5 flex-wrap">
            {me.is_demo && <span className="px-2 py-0.5 rounded-full bg-ochre/15 text-[#8a5a17] text-[12px] font-medium">{demoLabel}</span>}
            {me.profile?.verified && (
              <span className="px-2 py-0.5 rounded-full bg-leaf/15 text-leaf-deep text-[12px] font-medium inline-flex items-center gap-1">
                <ShieldCheck className="w-3 h-3" />{verifiedLabel ?? verifiedText()}
              </span>
            )}
          </div>
          {profile && (
            <button onClick={() => { setOpen(false); navigate(profile.to) }}
              className="mt-4 w-full min-h-[44px] rounded-full border border-soil-dark/15 text-sm font-medium flex items-center justify-center gap-2 hover:bg-cream">
              <UserRound className="w-4 h-4" />
              {profile.label}
            </button>
          )}
          {extra && (
            <button onClick={() => { setOpen(false); extra.onClick() }}
              className="mt-4 w-full min-h-[44px] rounded-full bg-leaf-deep text-cream text-sm font-medium flex items-center justify-center gap-2 hover:brightness-110">
              <Headphones className="w-4 h-4" />
              {extra.label}
            </button>
          )}
          {privacy && !me.is_demo && (
            <div className="mt-4 pt-3 border-t border-soil-dark/10">
              <p className="text-[13px] font-semibold text-soil-dark/80">{privacy.yourData}</p>
              {/* Closed by default: a farmer who came here to download or
                  delete should not have to scroll past a notice to reach the
                  button. Open, it is four short lines and no legal language. */}
              <details className="mt-1 group">
                <summary className="flex min-h-[44px] items-center gap-2 text-sm text-soil-dark/75 cursor-pointer list-none
                                    marker:content-none hover:text-soil-dark">
                  <ShieldCheck className="w-4 h-4 text-leaf" />
                  {privacy.what}
                </summary>
                <ul className="mb-1 space-y-1.5 pl-6 text-[13px] leading-snug text-soil-dark/75">
                  <li>{privacy.phone}</li>
                  <li>{privacy.cookie}</li>
                  <li>{privacy.noAds}</li>
                  <li>{privacy.server}</li>
                </ul>
              </details>
              <a href={api.myDataUrl} download
                className="flex min-h-[44px] w-full items-center gap-2 text-sm text-leaf-deep font-medium hover:underline">
                <Download className="w-4 h-4" />
                {privacy.downloadData}
              </a>
              {/* Delete sits apart from Download behind its own rule: the two
                  were 8px apart and a thumb aiming for one hit the other. */}
              {!erasing ? (
                <button onClick={() => setErasing(true)}
                  className="mt-4 pt-3 border-t border-soil-dark/10 flex min-h-[44px] w-full items-center gap-2 text-sm text-ember font-medium hover:underline">
                  <Trash2 className="w-4 h-4" />
                  {privacy.deleteAccount}
                </button>
              ) : (
                <div className="mt-4 rounded-xl bg-ember/5 border border-ember/20 p-3">
                  <p className="text-[13px] leading-snug text-soil-dark/80">{privacy.deleteWhat}</p>
                  <label className="mt-2 block text-[12px] text-soil-dark/75">{privacy.typeToConfirm}</label>
                  <input value={typed} onChange={(e) => setTyped(e.target.value)} autoFocus
                    aria-label={privacy.typeToConfirm}
                    className="mt-1 w-full min-h-[44px] rounded-lg border border-soil-dark/20 bg-white px-3 text-[16px]" />
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
                        className="mt-2 w-full min-h-[44px] rounded-full bg-ember text-cream text-sm font-semibold disabled:opacity-40">
                        {privacy.forever}
                      </button>
                      <button onClick={() => { setErasing(false); setTyped('') }}
                        className="mt-1.5 w-full min-h-[44px] rounded-full text-sm text-soil-dark/75 hover:bg-white">
                        {privacy.cancel}
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
          )}
          {/* No navigation here on purpose: RequireRole sees the session go
              and sends them to the front page itself, which cannot race with
              a redirect issued from this handler. */}
          <button onClick={() => { void logout() }}
            className={`${extra ? 'mt-2' : 'mt-4'} w-full min-h-[44px] rounded-full border border-soil-dark/15 text-sm font-medium flex items-center justify-center gap-2 hover:bg-cream`}>
            <LogOut className="w-4 h-4" />
            {logoutLabel}
          </button>
        </div>
      )}
    </div>
  )
}
