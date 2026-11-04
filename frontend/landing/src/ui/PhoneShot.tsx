/** A real screenshot of the app, in a plain phone frame.
 *
 *  The screenshots in public/demo are 402×778 captures of the farmer app, so
 *  the frame holds that ratio and nothing is cropped unless `crop` asks for a
 *  window onto part of the screen. No notch, no buttons, no reflections:
 *  the screen is the subject, the frame only says "this is a phone".
 */
export default function PhoneShot({ src, alt, crop, className = '' }: {
  src: string
  alt: string
  /** Show only part of the screen: a Tailwind aspect class plus an object-position. */
  crop?: { aspect: string; position: string }
  className?: string
}) {
  return (
    <div className={`rounded-[2rem] bg-soil-dark p-[7px] shadow-2xl shadow-black/30 ring-1 ring-black/20 ${className}`}>
      <img
        src={src}
        alt={alt}
        loading="lazy"
        decoding="async"
        width={402}
        height={778}
        className={`block w-full rounded-[1.6rem] bg-cream object-cover ${
          crop ? `${crop.aspect} ${crop.position}` : 'aspect-[402/778]'}`}
      />
    </div>
  )
}
