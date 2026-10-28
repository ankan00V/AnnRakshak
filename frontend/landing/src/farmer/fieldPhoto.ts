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
  src: string
}

const STANDING: Record<string, FieldPhoto> = {
  rice: { src: '/field/rice.webp' },
  maize: { src: '/field/maize.webp' },
  cotton: { src: '/field/cotton.webp' },
  soybean: { src: '/field/soybean.webp' },
}

/** The bare field after the crop comes off: stubble ploughed under. */
const HARVESTED: FieldPhoto = { src: '/field/harvested.webp' }

export function fieldPhoto(farm: { crop: string; status?: string }): FieldPhoto | null {
  if (farm.status === 'fallow') return HARVESTED
  return STANDING[farm.crop] ?? null
}
