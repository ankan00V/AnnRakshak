import type { ReactNode } from 'react'
import FootageBackdrop from './FootageBackdrop'

/** A full-bleed band of the field, with one line over it.
 *
 *  The page cuts hard between its sections — cream, then green, then dark —
 *  and the joins were doing nothing but changing colour. A band of the real
 *  ground at the join gives the eye somewhere to rest and carries one line
 *  that belongs to both sides of it.
 *
 *  All of this footage is ours, shot in the field, which is why it can sit
 *  full-bleed without a credit under it.
 *
 *  A band is a join, not a section: it holds one short line and never a
 *  heading, a control or anything a reader has to work at. If it needs more
 *  than that it should be a section instead.
 *
 *  And it has to show something the product does. Footage placed because it
 *  is pretty, under a line written to fit whatever the shot happens to be,
 *  reads as filler — three such bands were cut for exactly that. Today there
 *  is one: the field being readied for a new season, at the head of How it
 *  works, because a season's first day is where the app starts counting.
 *
 *  Video bands cost about half a megabyte each, so they use FootageBackdrop,
 *  which fetches nothing until the band is nearly in view and nothing at all
 *  on a save-data or 2g connection, or for a reader who asked for less
 *  motion. A still band costs its image and nothing else; `loading="lazy"`
 *  keeps it off the critical path the same way.
 */
export default function FootageBand({
  src,
  poster,
  still,
  alt = '',
  objectClass = 'object-center',
  children,
  className = '',
}: {
  /** A clip, with its poster. Leave both out for a still band. */
  src?: string
  poster?: string
  /** A still instead of a clip. One of `src` or `still` is required. */
  still?: string
  /** Only used by a still band; a clip is decorative and stays aria-hidden. */
  alt?: string
  /** Which part of the frame survives the crop. */
  objectClass?: string
  /** The line. Kept short enough to read in one glance while scrolling. */
  children?: ReactNode
  className?: string
}) {
  // A scrim dark enough for cream type at every width. Heavier at the foot,
  // where the line sits, and heavier again on a phone, where the frame is
  // cropped hard and there is more going on behind less type.
  const scrim = (
    <>
      <div className="absolute inset-0 bg-soil-dark/55 md:bg-soil-dark/40" />
      <div className="absolute inset-0 bg-gradient-to-b from-soil-dark/35 via-transparent to-soil-dark/80" />
    </>
  )

  return (
    <div
      className={`relative w-full overflow-hidden h-[clamp(200px,34vw,360px)] ${className}`}
    >
      {src && poster ? (
        <FootageBackdrop src={src} poster={poster} objectClass={objectClass} scrim={scrim} />
      ) : (
        <div className="absolute inset-0 overflow-hidden">
          <img
            src={still}
            alt={alt}
            loading="lazy"
            decoding="async"
            className={`w-full h-full object-cover ${objectClass}`}
          />
          {scrim}
        </div>
      )}

      {children && (
        <div className="relative h-full flex items-end">
          <p
            className="w-full max-w-6xl mx-auto px-6 md:px-12 pb-7 md:pb-10
                       font-instrument-serif text-cream text-balance
                       text-xl sm:text-2xl md:text-3xl leading-snug
                       [text-shadow:0_1px_18px_rgba(20,22,15,0.45)]"
          >
            {children}
          </p>
        </div>
      )}
    </div>
  )
}
