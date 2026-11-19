import { Camera } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useFarmer } from '../FarmerContext'
import { PANEL, PRIMARY } from '../tokens'

const BANNER = 9 / 16  // the banner's height over its width

/** A photo the model found unfamiliar as a whole, with one part that looks
 *  like the photos it learnt from: that part, shown large, and a way to
 *  photograph it up close. A close-up goes through every check from the start;
 *  the first photo still waits for the expert.
 *
 *  `region` is [x0, y0, x1, y1] as fractions of the photo's central square, the
 *  square the model reads. The banner draws the photo into that square and
 *  enlarges it so the region fills the banner's width. */
export default function CloserLook({ imageUrl, region }: { imageUrl: string | null; region: number[] }) {
  const { t } = useFarmer()
  const [x0, y0, x1, y1] = region
  const w = x1 - x0
  return (
    <section className={`${PANEL} p-5 lg:p-6`}>
      {/* The part as a banner across the card, the words under it: the card
          sits in a column that is narrow on a laptop, and text squeezed beside
          a picture there breaks a word to a line. The region spans the banner's
          width and is centred in its height. */}
      {imageUrl && (
        <div className="relative aspect-[16/9] overflow-hidden rounded-[18px] bg-leaf-deep">
          <div
            className="absolute"
            style={{
              width: `${100 / w}%`,
              height: `${100 / w / BANNER}%`,
              left: `${(-x0 / w) * 100}%`,
              top: `${((BANNER / 2 - (y0 + y1) / 2 / w) / BANNER) * 100}%`,
            }}
          >
            <img src={imageUrl} alt="" className="h-full w-full object-cover" />
          </div>
        </div>
      )}
      <h2 className="mt-4 font-instrument-serif text-[26px] leading-tight text-leaf-deep">{t('closerTitle')}</h2>
      <p className="mt-1.5 text-[15px] text-soil-dark/85">{t('closerBody')}</p>
      <Link to="/app/scan" className={`${PRIMARY} mt-5`}>
        <Camera className="h-5 w-5" aria-hidden /> {t('closerCta')}
      </Link>
    </section>
  )
}
