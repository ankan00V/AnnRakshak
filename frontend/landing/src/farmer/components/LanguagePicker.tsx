import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Check, ChevronDown, Languages, X } from 'lucide-react'
import type { Lang } from '../../api/types'
import { AUTHORED, LANGS } from '../../lib/i18n'
import { useFarmer } from '../FarmerContext'
import { lockScroll, onEscape } from '../../lib/sheet'

/** All eleven languages in their own script. `grid` for onboarding, the
 *  default is the header button that opens a sheet.
 *
 *  `wide` is whether the grid has a page to spread across: five abreast under
 *  a sign-up form, two in a side column that is a third of one. */
export default function LanguagePicker({ onPick, variant = 'button', wide = true, light = false }: {
  onPick: (lang: Lang) => void
  variant?: 'button' | 'grid'
  /** On a light top bar: a white pill with dark text instead of a glass one. */
  light?: boolean
  wide?: boolean
}) {
  const { lang, t } = useFarmer()
  const [open, setOpen] = useState(false)
  const current = LANGS.find((l) => l.code === lang)
  const opener = useRef<HTMLButtonElement>(null)
  const sheet = useRef<HTMLDivElement>(null)

  // A sheet that a screen reader is never moved into is invisible to it, and
  // one the page scrolls behind loses its place on a phone. Same pattern as
  // the photo zoom on the live result: land on the current language, Escape
  // closes, the page stays still, and focus goes back to the pill after.
  useEffect(() => {
    if (!open) return
    const back = opener.current
    const box = sheet.current
    ;(box?.querySelector<HTMLButtonElement>('[aria-current="true"]')
      ?? box?.querySelector<HTMLButtonElement>('button[lang]'))?.focus()
    const release = lockScroll()
    const unEsc = onEscape(() => setOpen(false))
    return () => {
      unEsc()
      release()
      back?.focus()
    }
  }, [open])

  const soon = LANGS.filter((l) => !l.ready)
  const grid = (
    <div className={`grid grid-cols-2 gap-2 ${variant === 'grid' && wide ? 'lg:grid-cols-5' : ''}`}>
      {LANGS.filter((l) => l.ready).map((l) => (
        <button key={l.code} onClick={() => { onPick(l.code); setOpen(false) }} lang={l.code}
          aria-current={l.code === lang ? 'true' : undefined}
          className={`min-h-[56px] rounded-2xl border px-3 py-2 text-left flex items-center gap-2 transition-colors ${
            l.code === lang ? 'border-leaf-deep bg-leaf/10' : 'border-soil-dark/10 bg-white hover:border-leaf/40'}`}>
          <span className="flex-1 min-w-0">
            <span className="block text-base font-semibold leading-tight">{l.label}</span>
            <span className="block text-[12px] text-soil-dark/70">{l.english}</span>
          </span>
          {l.code === lang && <Check className="w-4 h-4 text-leaf-deep shrink-0" />}
        </button>
      ))}
      {soon.length > 0 && (
        <p className="col-span-full text-[12px] text-soil-dark/70 pt-1">
          {t('comingSoon')}: {soon.map((l) => l.label).join(' · ')}
        </p>
      )}
    </div>
  )

  if (variant === 'grid') {
    return (
      <div className="space-y-2">
        {grid}
        {!AUTHORED.includes(lang) && <p className="text-[12px] text-soil-dark/70">{t('machineNote')}</p>}
      </div>
    )
  }

  return (
    <>
      {/* On a phone this pill was 88px of a 375px header — wider than the
          bell and the avatar together — and the width came out of the field
          line beside it, which is the one thing in the header a farmer needs
          to read: "Rice (paddy) · Bhandara" wants 125px and was given 85, so
          it was cut mid-village on every screen of the app.

          Below `sm` the language name goes and the glyph stays. The pill is
          still a 44px target, still says what it does to a screen reader, and
          the sheet it opens still lists every language in its own script —
          which is the screen that has to be readable without English, not
          this button. */}
      <button ref={opener} data-tour="lang" onClick={() => setOpen(true)} aria-label={t('chooseLanguage')}
        aria-haspopup="dialog" aria-expanded={open}
        className={`flex items-center gap-1.5 rounded-full px-2.5 sm:px-3.5 min-w-[44px] min-h-[44px] justify-center font-medium transition-colors ${
          light ? 'bg-white text-soil-dark text-sm shadow-[0_4px_14px_-8px_rgba(43,29,18,0.35)] ring-1 ring-soil-dark/5 hover:bg-cream'
            : 'bg-cream/10 hover:bg-cream/20 text-xs'}`}>
        <Languages className="w-4 h-4 shrink-0" />
        <span className="hidden sm:inline">{current?.label}</span>
        {light && <ChevronDown className="hidden sm:block w-3.5 h-3.5 shrink-0 opacity-70" aria-hidden />}
      </button>
      {open && createPortal(
        <div className="fixed inset-0 z-50 bg-black/40 flex items-end sm:items-center justify-center" onClick={() => setOpen(false)}>
          <div ref={sheet} role="dialog" aria-modal="true" aria-label={t('chooseLanguage')} onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md bg-cream text-soil-dark rounded-t-3xl sm:rounded-3xl p-4 pb-[max(1rem,env(safe-area-inset-bottom))] max-h-[85vh] overflow-y-auto overscroll-contain animate-fadein">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold">{t('chooseLanguage')}</h2>
              <button aria-label={t('krishiClose')} onClick={() => setOpen(false)}
                className="-m-2 w-11 h-11 rounded-full text-soil-dark/70 hover:bg-soil-dark/5 hover:text-soil-dark flex items-center justify-center">
                <X className="w-5 h-5" />
              </button>
            </div>
            {grid}
            {!AUTHORED.includes(lang) && <p className="mt-3 text-[12px] text-soil-dark/70">{t('machineNote')}</p>}
          </div>
        </div>,
        document.body,  // outside the sticky header's stacking context, above the nav
      )}
    </>
  )
}
