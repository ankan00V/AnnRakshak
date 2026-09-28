import { useEffect, useRef, useState, type ReactNode } from 'react'

/** A section that lifts into place the first time it is scrolled to.
 *
 *  Visible by default: the hidden state is only applied after mount, and only
 *  when the browser reports motion is welcome. A headless renderer, a paused
 *  tab or a reader who asked for less motion all get the content as it is,
 *  never a blank band waiting for a transition that will not fire.
 */
export default function Reveal({ children, delay = 0, className = '' }: {
  children: ReactNode; delay?: number; className?: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [state, setState] = useState<'static' | 'hidden' | 'shown'>('static')

  useEffect(() => {
    const el = ref.current
    if (!el || !('IntersectionObserver' in window)) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    if (el.getBoundingClientRect().top < window.innerHeight) return  // already on screen at load
    setState('hidden')
    const io = new IntersectionObserver(([e]) => {
      // Also show anything the reader has already scrolled past: a fast flick can
      // carry a section by between two observer samples, and a band that stays
      // invisible for the rest of the session is far worse than no animation.
      if (e.isIntersecting || e.boundingClientRect.top < 0) {
        setState('shown')
        io.disconnect()
      }
    }, { rootMargin: '0px 0px -12% 0px' })
    io.observe(el)
    return () => io.disconnect()
  }, [])

  return (
    <div
      ref={ref}
      style={state === 'shown' ? { transitionDelay: `${delay}ms` } : undefined}
      className={`${className} ${
        state === 'hidden' ? 'opacity-0 translate-y-5' : 'opacity-100 translate-y-0'
      } transition-[opacity,transform] duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]`}
    >
      {children}
    </div>
  )
}
