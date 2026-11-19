import { useId } from 'react'

/** Solid, two-tone glyphs for the landing page's feature strip.
 *  Outline icons read as thin and grey at this size against cream and deep
 *  green; these are filled, with a lighter top edge, like the leaves they
 *  stand for. */

type P = { className?: string }

function Grad({ id, from, to }: { id: string; from: string; to: string }) {
  return (
    <defs>
      <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor={from} /><stop offset="1" stopColor={to} />
      </linearGradient>
    </defs>
  )
}

export function LeafSolid({ className, from = '#7cc24a', to = '#2f7a2a' }: P & { from?: string; to?: string }) {
  const id = useId()
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <Grad id={id} from={from} to={to} />
      <path fill={`url(#${id})`}
        d="M20.6 3.2C11.4 3.1 4.4 7.6 4.4 15c0 1.8.5 3.3 1.3 4.5C7 15 10.2 11.5 14.8 9.3c-3.9 2.8-6.6 6.3-7.9 10.6 1.2.7 2.6 1 4.1 1 7.4 0 10.8-7.4 9.6-17.7Z" />
    </svg>
  )
}

export function SprayBottleSolid({ className }: P) {
  const id = useId()
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <Grad id={id} from="#4e9a3c" to="#2a6a2c" />
      <g fill={`url(#${id})`}>
        <path d="M7.5 2.5h7.2c.5 0 1 .2 1.3.6l1.9 2.2c.3.4 0 .9-.4.9H11.6l.4 2.3H9.1l.3-2.3H7.5a.9.9 0 0 1-.9-.9V3.4c0-.5.4-.9.9-.9Z" />
        <path d="M18.3 3.6h1.8c.4 0 .6.4.4.7l-.7 1c-.2.2-.5.2-.7 0l-.8-1c-.2-.3 0-.7 0-.7Z" />
        <path d="M8.6 9.2h4.8c.4 0 .7.3.8.6l.9 2.4c.3.6.4 1.3.4 2v6.2c0 1-.8 1.8-1.8 1.8H8.3c-1 0-1.8-.8-1.8-1.8v-6.2c0-.7.1-1.4.4-2l.9-2.4c.1-.3.4-.6.8-.6Z" />
      </g>
      <rect x="8.4" y="14.2" width="5.2" height="4.4" rx="0.8" fill="#fff" fillOpacity="0.9" />
    </svg>
  )
}

export function SunSolid({ className }: P) {
  const id = useId()
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <defs>
        <radialGradient id={id} cx="0.4" cy="0.35" r="0.7">
          <stop offset="0" stopColor="#ffd25e" /><stop offset="1" stopColor="#f39a1c" />
        </radialGradient>
      </defs>
      <circle cx="12" cy="12" r="5" fill={`url(#${id})`} />
      <g stroke="#f4a325" strokeWidth="1.7" strokeLinecap="round">
        <path d="M12 1.8v2.4M12 19.8v2.4M1.8 12h2.4M19.8 12h2.4M4.8 4.8l1.7 1.7M17.5 17.5l1.7 1.7M4.8 19.2l1.7-1.7M17.5 6.5l1.7-1.7" />
      </g>
    </svg>
  )
}

export function BellSolid({ className }: P) {
  const id = useId()
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <Grad id={id} from="#4e9a3c" to="#2a6a2c" />
      <path fill={`url(#${id})`}
        d="M12 2.3c.8 0 1.5.7 1.5 1.5v.7a6.2 6.2 0 0 1 4.7 6v3.7l1.7 2.6c.4.7 0 1.6-.9 1.6H5c-.9 0-1.3-.9-.9-1.6l1.7-2.6v-3.7a6.2 6.2 0 0 1 4.7-6v-.7c0-.8.7-1.5 1.5-1.5Z" />
      <path fill="#2a6a2c" d="M9.4 19.6h5.2a2.6 2.6 0 0 1-5.2 0Z" />
    </svg>
  )
}
