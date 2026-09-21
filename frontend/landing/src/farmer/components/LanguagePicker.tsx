import { useState } from 'react'
import { createPortal } from 'react-dom'
import { Check, Languages, X } from 'lucide-react'
import type { Lang } from '../../api/types'
import { AUTHORED, LANGS } from '../../lib/i18n'
import { useFarmer } from '../FarmerContext'

/** All eleven languages in their own script. `grid` for onboarding, the
 *  default is the header button that opens a sheet. */
export default function LanguagePicker({ onPick, variant = 'button' }: {
  onPick: (lang: Lang) => void
  variant?: 'button' | 'grid'
}) {
  const { lang, t } = useFarmer()
  const [open, setOpen] = useState(false)
  const current = LANGS.find((l) => l.code === lang)

  const soon = LANGS.filter((l) => !l.ready)
  const grid = (
    <div className={`grid grid-cols-2 gap-2 ${variant === 'grid' ? 'lg:grid-cols-5' : ''}`}>
      {LANGS.filter((l) => l.ready).map((l) => (
        <button key={l.code} onClick={() => { onPick(l.code); setOpen(false) }} lang={l.code}
          className={`min-h-[56px] rounded-2xl border px-3 py-2 text-left flex items-center gap-2 transition-colors ${
            l.code === lang ? 'border-leaf-deep bg-leaf/10' : 'border-soil-dark/10 bg-white hover:border-leaf/40'}`}>
          <span className="flex-1 min-w-0">
            <span className="block text-base font-semibold leading-tight">{l.label}</span>
            <span className="block text-[11px] text-soil-dark/50">{l.english}</span>
          </span>
          {l.code === lang && <Check className="w-4 h-4 text-leaf-deep shrink-0" />}
        </button>
      ))}
      {soon.length > 0 && (
        <p className="col-span-full text-[11px] text-soil-dark/50 pt-1">
          {t('comingSoon')}: {soon.map((l) => l.label).join(' · ')}
        </p>
      )}
    </div>
  )

  if (variant === 'grid') {
    return (
      <div className="space-y-2">
        {grid}
        {!AUTHORED.includes(lang) && <p className="text-[11px] text-soil-dark/55">{t('machineNote')}</p>}
      </div>
    )
  }

  return (
    <>
      <button onClick={() => setOpen(true)} aria-label={t('chooseLanguage')}
        className="flex items-center gap-1.5 rounded-full bg-cream/10 hover:bg-cream/20 px-3 min-h-[36px] text-xs font-medium">
        <Languages className="w-4 h-4" />
        {current?.label}
      </button>
      {open && createPortal(
        <div className="fixed inset-0 z-50 bg-black/40 flex items-end sm:items-center justify-center" onClick={() => setOpen(false)}>
          <div role="dialog" aria-label={t('chooseLanguage')} onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md bg-cream text-soil-dark rounded-t-3xl sm:rounded-3xl p-4 pb-[max(1rem,env(safe-area-inset-bottom))] max-h-[85vh] overflow-y-auto animate-fadein">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold">{t('chooseLanguage')}</h2>
              <button aria-label="Close" onClick={() => setOpen(false)} className="w-9 h-9 rounded-full hover:bg-soil-dark/5 flex items-center justify-center">
                <X className="w-4 h-4" />
              </button>
            </div>
            {grid}
            {!AUTHORED.includes(lang) && <p className="mt-3 text-[11px] text-soil-dark/55">{t('machineNote')}</p>}
          </div>
        </div>,
        document.body,  // outside the sticky header's stacking context, above the nav
      )}
    </>
  )
}
