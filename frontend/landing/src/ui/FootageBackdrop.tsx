import { useEffect, useRef, useState, type ReactNode } from 'react'

/** Our own field footage, playing behind a panel that was already there.
 *
 *  Used twice: behind the closing block, which asks whether you are ready to
 *  protect your harvest, and behind the two audience columns, so the alert a
 *  farmer reads and the map an officer works from sit over the field they are
 *  both about. Neither costs the page any height — the backdrop is absolutely
 *  positioned inside a panel that already existed, which is the only reason
 *  either belongs.
 *
 *  A clip is around a megabyte, which on a village connection is not nothing,
 *  so it is only fetched once its panel is about to be seen, and not at all on
 *  a save-data or 2g connection, or for a reader who asked for less motion.
 *  They get the poster, which is a frame of the same shot, and the panel looks
 *  deliberate either way.
 *
 *  `scrim` is passed in rather than fixed here because each panel has its own
 *  problem to solve: one has to stay the brand's green under cream type, the
 *  other has to keep two columns of text crisp over a sunlit field.
 */
type Connection = { saveData?: boolean; effectiveType?: string }

export default function FootageBackdrop({ src, poster, objectClass = 'object-center', scrim }: {
  src: string
  poster: string
  /** Which part of the frame survives the crop. */
  objectClass?: string
  scrim: ReactNode
}) {
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
        poster={poster}
        src={wanted ? src : undefined}
        preload="none"
        autoPlay
        muted
        loop
        playsInline
        tabIndex={-1}
        className={`w-full h-full object-cover ${objectClass}`}
      />
      {scrim}
    </div>
  )
}
