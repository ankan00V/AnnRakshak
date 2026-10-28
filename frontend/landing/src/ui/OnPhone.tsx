import { useState, type ReactNode } from 'react'
import { ChevronDown } from 'lucide-react'
import { useWide } from '../lib/hooks'

/** Detail that a phone shows on request and a desktop shows outright.
 *
 *  The page has to make its case to somebody holding a phone, and the case is
 *  made by the headings and the numbers. The evidence underneath them — a
 *  whole alert card in Marathi, a district map, a model's score broken into
 *  three figures — is what makes it worth believing, and is also what turned
 *  the page into eleven screens of scrolling.
 *
 *  So on a phone it is one line you can open, and nothing is taken away: the
 *  claim stays visible, the proof is one tap under it. Above the phone
 *  breakpoint this renders its children and nothing else, so the desktop page
 *  is exactly what it was.
 */
export default function OnPhone({ label, children, className = '' }: {
  /** What the reader is opening, named so the tap is worth making. */
  label: string
  children: ReactNode
  className?: string
}) {
  const wide = useWide(640)
  const [open, setOpen] = useState(false)

  if (wide) return <>{children}</>

  return (
    <div className={className}>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="w-full min-h-[44px] flex items-center justify-between gap-3 rounded-xl
                   border border-current/15 px-3.5 text-left text-[13px] font-medium opacity-80"
      >
        {label}
        <ChevronDown className={`w-4 h-4 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && <div className="mt-3">{children}</div>}
    </div>
  )
}
