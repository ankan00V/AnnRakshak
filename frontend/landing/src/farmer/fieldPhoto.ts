/** A photograph of the state this field is in.
 *
 *  Chosen by what the field is actually doing rather than hung on a screen as
 *  decoration: a farmer who reads little should be able to tell a standing
 *  crop from a cut one without reading the sentence that says so. Every one is
 *  a real photograph of a real field.
 *
 *  Who took each one, and what we may do with it, is recorded in
 *  public/field/CREDITS.md rather than printed under the picture: a farmer
 *  deciding whether their crop looks like this has no use for a photographer's
 *  name.
 */
export interface FieldPhoto {
  /** The full-size original, for wide screens and as the fallback. */
  src: string
  /** `<img srcSet>`: the phone-sized copy first, then the original. */
  srcSet: string
  /** `<img sizes>` for the Home field card: the width this photo is drawn
   *  at there, which for a wide photo is wider than the card. */
  sizes: string
  /** The original's pixel size, for `<img width height>` (no layout jump). */
  width: number
  height: number
}

/** Photographs that also ship a phone-sized copy beside the original, named
 *  `<name>-<w>.webp`. The originals are 1280-1800 px wide and 80-200 KB; a
 *  360-412 px phone at 2x needs about 800, and on 2G the difference is
 *  seconds of a blank card. Add a row here when you add a resized file. */
const SIZES: Record<string, { w: number; h: number; small: number }> = {
  '/photos/hills.webp': { w: 1800, h: 748, small: 900 },
  '/photos/rice-banner.webp': { w: 1444, h: 570, small: 800 },
  '/field/maize.webp': { w: 1280, h: 716, small: 800 },
  '/field/cotton.webp': { w: 1280, h: 404, small: 800 },
  '/field/soybean.webp': { w: 1280, h: 352, small: 800 },
  '/field/harvested.webp': { w: 1280, h: 716, small: 800 },
}

/** The phone-sized copy of a photo, or the photo itself when it has none. */
export function smallPhoto(src: string): string {
  const s = SIZES[src]
  return s ? src.replace(/\.webp$/, `-${s.small}.webp`) : src
}

/** A ready `srcSet` for any photo in SIZES (undefined otherwise, which an
 *  `<img>` treats as absent). e.g. for the hills band:
 *  `<img src="/photos/hills.webp" srcSet={photoSrcSet('/photos/hills.webp')} sizes="100vw" />` */
export function photoSrcSet(src: string): string | undefined {
  const s = SIZES[src]
  return s ? `${smallPhoto(src)} ${s.small}w, ${src} ${s.w}w` : undefined
}

/* The Home field card: the content column less its padding (at most 400 px
 * below lg, where the column is max-w-md) and 230 px tall; from lg about 700 px
 * wide and 250 px tall. object-cover draws a photo wider than its box at the
 * box's height, so the width it is drawn at is the larger of the two, and that
 * is what the browser must choose a file by. A 1280x352 soybean field is
 * ~840 px wide on a 360 px phone, not 360: told "100vw", the browser fetched
 * the 800 copy and drew it soft at 2x. */
const CARD = { phone: { w: 400, h: 230 }, wide: { w: 700, h: 250 } }
const drawn = (box: { w: number; h: number }, w: number, h: number) => Math.max(box.w, Math.ceil(box.h * w / h))

function photo(src: string): FieldPhoto {
  const s = SIZES[src]
  const width = s?.w ?? 1444
  const height = s?.h ?? 570
  return {
    src,
    srcSet: photoSrcSet(src) ?? '',
    // Worked out here, per photo, so `sizes` is one plain length per
    // breakpoint and asks nothing of the browser's CSS math.
    sizes: `(min-width: 1024px) ${drawn(CARD.wide, width, height)}px, ${drawn(CARD.phone, width, height)}px`,
    width,
    height,
  }
}

const STANDING: Record<string, FieldPhoto> = {
  // The paddy in full ear from the app's own photo set, the same one Home leads with.
  rice: photo('/photos/rice-banner.webp'),
  maize: photo('/field/maize.webp'),
  cotton: photo('/field/cotton.webp'),
  soybean: photo('/field/soybean.webp'),
}

/** The bare field after the crop comes off: stubble ploughed under. */
const HARVESTED: FieldPhoto = photo('/field/harvested.webp')

export function fieldPhoto(farm: { crop: string; status?: string }): FieldPhoto | null {
  if (farm.status === 'fallow') return HARVESTED
  return STANDING[farm.crop] ?? null
}
