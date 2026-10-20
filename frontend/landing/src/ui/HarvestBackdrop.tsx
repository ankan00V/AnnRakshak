import { useEffect, useRef, useState } from 'react'

/** Our own footage of a paddy harvest, sitting behind the closing block.
 *
 *  It earns its place by being the thing the page has spent its whole length
 *  arguing for — and by costing the page no extra height: it fills a panel
 *  that was a flat colour before.
 *
 *  Three quarters of a megabyte is not nothing on a village connection, so it
 *  is only fetched once it is about to be seen, and only if the connection has
 *  not asked us not to. A reader who prefers less motion, a phone on 2g and a
 *  browser saving data all get the poster instead — the same frame, and the
 *  panel looks deliberate either way.
 */
const SRC = '/footage/harvest.mp4'
const POSTER = '/footage/harvest-poster.webp'

type Connection = { saveData?: boolean; effectiveType?: string }

export default function HarvestBackdrop() {
  const ref = useRef<HTMLVideoElement>(null)
  const [wanted, setWanted] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el || !('IntersectionObserver' in window)) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const net = (navigator as Navigator & { connection?: Connection }).connection
    if (net?.saveData || /(^|-)2g$/.test(net?.effectiveType ?? '')) return

    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) {
        setWanted(true)
        // First time through there is no source yet, and the autoPlay
        // attribute starts it the moment React attaches one. Only a return
        // visit, after the pause below, needs the nudge.
        if (el.currentSrc) void el.play().catch(() => {})
      } else {
        // A loop running far off screen is somebody's battery for nothing.
        el.pause()
      }
    }, { rootMargin: '300px 0px' })
    io.observe(el)
    return () => io.disconnect()
  }, [])

  return (
    <div aria-hidden className="absolute inset-0 overflow-hidden">
      <video
        ref={ref}
        poster={POSTER}
        src={wanted ? SRC : undefined}
        preload="none"
        autoPlay
        muted
        loop
        playsInline
        tabIndex={-1}
        // Biased downward: the crop that matters is the cut field and the
        // combine in it, not the rooftops along the top of the frame.
        className="w-full h-full object-cover object-[center_72%]"
      />
      {/* The panel stays the brand's green and keeps cream type readable over
          a sunlit field: an even tint to hold the colour, then a scrim that is
          solid where the small type sits and opens up behind the headline. */}
      {/* A phone crops a landscape frame hard, so the combine lands right
          behind the headline rather than off in the field. Narrow screens get
          a heavier tint to keep the type first. */}
      <div className="absolute inset-0 bg-leaf-deep/65 md:bg-leaf-deep/45" />
      <div className="absolute inset-0 bg-cta-scrim" />
    </div>
  )
}
