/** A photograph of the state this field is in.
 *
 *  Chosen by what the field is actually doing rather than hung on a screen as
 *  decoration: a farmer who reads little should be able to tell a standing
 *  crop from a cut one without reading the sentence that says so. Every one is
 *  a real photograph of a real field.
 *
 *  Rice, maize and the bare field are ours. We had no photograph of a cotton
 *  or a soybean field, so those two are other people's, used under their
 *  licences — and where a licence asks for a credit, the credit is shown under
 *  the picture, because a line in a file nobody opens is not attribution.
 *  public/field/CREDITS.md has the full record.
 */
export interface FieldPhoto {
  src: string
  /** Shown under the picture when the licence asks for it. Ours carry none. */
  credit?: string
}

const STANDING: Record<string, FieldPhoto> = {
  rice: { src: '/field/rice.webp' },
  maize: { src: '/field/maize.webp' },
  cotton: { src: '/field/cotton.webp', credit: 'Bhaskaranaidu · CC BY-SA 3.0 · cropped' },
  soybean: { src: '/field/soybean.webp' },
}

/** The bare field after the crop comes off: stubble ploughed under. */
const HARVESTED: FieldPhoto = { src: '/field/harvested.webp' }

export function fieldPhoto(farm: { crop: string; status?: string }): FieldPhoto | null {
  if (farm.status === 'fallow') return HARVESTED
  return STANDING[farm.crop] ?? null
}
