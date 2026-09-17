import { useState } from 'react'
import { Link } from 'react-router-dom'
import { smoothScrollTo } from './smoothScroll'
import BrandMark from './ui/BrandMark'
import { useAuth } from './auth/AuthContext'
import { homeOf } from './auth/helpers'
import LanguagePicker from './farmer/components/LanguagePicker'
import { useFarmer } from './farmer/FarmerContext'

const EASE = 'ease-[cubic-bezier(0.76,0,0.24,1)]'

const NAV_ITEMS = [
  { label: 'How It Works', id: 'how-it-works' },
  { label: 'Features', id: 'features' },
  { label: 'Impact', id: 'impact' },
  { label: 'For Officials', id: 'for-officials' },
]

const MENU_ITEMS = [...NAV_ITEMS, { label: 'Contact', id: 'contact' }]

function Hamburger({ open, onClick }: { open: boolean; onClick: () => void }) {
  const line = `block h-[2px] rounded-full bg-white transition-all duration-500 ${EASE}`
  return (
    <button
      onClick={onClick}
      aria-label="Open menu"
      aria-expanded={open}
      className="flex flex-col gap-[5px] p-2 -m-2 md:hidden"
    >
      <span className={`${line} w-6 ${open ? 'translate-y-[7px] rotate-45' : ''}`} />
      <span className={`${line} ${open ? 'w-6 opacity-0' : 'w-4'}`} />
      <span className={`${line} w-6 ${open ? '-translate-y-[7px] -rotate-45' : ''}`} />
    </button>
  )
}

export default function Navbar() {
  const [open, setOpen] = useState(false)
  const { me } = useAuth()
  const { t, setLang } = useFarmer()
  const account = me
    ? { to: homeOf(me.role), label: t(me.role === 'expert' ? 'landOpenConsole' : 'landOpenApp') }
    : { to: '/login', label: t('authLogin') }

  const go = (id: string) => {
    setOpen(false)
    smoothScrollTo(id)
  }

  return (
    <>
      <nav className="flex items-center justify-between px-6 md:px-12 lg:px-16 py-5 md:py-6">
        <div className="flex items-center gap-8 lg:gap-12">
          <span className="flex items-center gap-2.5 text-white font-semibold text-lg tracking-tight font-sans">
            <BrandMark size={36} />
            AnnRakshak
          </span>
          <div className="hidden md:flex items-center gap-8">
            {NAV_ITEMS.map(({ label, id }) => (
              <button
                key={id}
                onClick={() => smoothScrollTo(id)}
                className="text-white/80 hover:text-white text-sm font-light transition-colors duration-200"
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-6">
          <button
            onClick={() => smoothScrollTo('contact')}
            className="hidden md:block text-white/80 hover:text-white text-sm font-light transition-colors duration-200"
          >
            Contact
          </button>
          <span className="text-white [&_button]:bg-white/15 [&_button]:hover:bg-white/25">
            <LanguagePicker onPick={setLang} />
          </span>
          <Link
            to={account.to}
            className="hidden md:block text-white/80 hover:text-white text-sm font-light transition-colors duration-200"
          >
            {account.label}
          </Link>
          {!me && (
            <Link
              to="/signup"
              className="hidden md:inline-block bg-white text-black rounded-full px-5 py-2 text-sm font-medium"
            >
              {t('authCreateAccount')}
            </Link>
          )}
          <Hamburger open={open} onClick={() => setOpen(true)} />
        </div>
      </nav>

      <div
        className={`fixed inset-0 z-50 md:hidden transition-opacity duration-700 ${EASE} ${
          open ? 'opacity-100' : 'opacity-0 pointer-events-none'
        }`}
      >
        <div className="absolute inset-0 bg-black/90 backdrop-blur-xl" />

        <div
          className={`relative z-10 flex flex-col h-full transition-opacity duration-700 ${EASE} ${
            open ? 'opacity-100' : 'opacity-0'
          }`}
        >
          <div className="flex items-center justify-between px-6 py-5">
            <span className="flex items-center gap-2.5 text-white font-semibold text-lg tracking-tight font-sans">
              <BrandMark size={36} />
              AnnRakshak
            </span>
            <button
              onClick={() => setOpen(false)}
              aria-label="Close menu"
              className="flex flex-col gap-[5px] p-2 -m-2"
            >
              <span
                className={`block w-6 h-[2px] rounded-full bg-white rotate-45 transition-transform duration-500 ${EASE}`}
              />
              <span
                className={`block w-6 h-[2px] rounded-full bg-white -rotate-45 transition-transform duration-500 ${EASE}`}
              />
            </button>
          </div>

          <nav className="flex-1 flex flex-col justify-center">
            {MENU_ITEMS.map(({ label, id }, i) => (
              <button
                key={id}
                onClick={() => go(id)}
                style={{ transitionDelay: open ? `${150 + i * 80}ms` : '0ms' }}
                className={`text-4xl sm:text-5xl font-instrument-serif text-white text-center border-b border-white/10 py-4 hover:pl-4 transition-all duration-700 ${EASE} ${
                  open ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'
                }`}
              >
                {label}
              </button>
            ))}
          </nav>

          <div className="px-6 pb-10 space-y-3">
            <Link
              to={me ? account.to : '/signup'}
              style={{ transitionDelay: open ? '550ms' : '0ms' }}
              className={`block w-full bg-white text-black text-center rounded-full py-4 text-sm font-medium transition-opacity duration-700 ${EASE} ${
                open ? 'opacity-100' : 'opacity-0'
              }`}
            >
              {me ? account.label : t('authCreateAccount')}
            </Link>
            {!me && (
              <Link
                to="/login"
                style={{ transitionDelay: open ? '600ms' : '0ms' }}
                className={`block w-full border border-white/40 text-white text-center rounded-full py-4 text-sm font-medium transition-opacity duration-700 ${EASE} ${
                  open ? 'opacity-100' : 'opacity-0'
                }`}
              >
                {t('authLogin')}
              </Link>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
