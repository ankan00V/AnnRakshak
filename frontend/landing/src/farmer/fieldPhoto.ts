/** A photograph of the state this field is in.
 *
 *  Our own, taken in real fields, and chosen by what the field is actually
 *  doing rather than hung on the screen as decoration: a farmer who reads
 *  little should be able to tell a standing crop from a cut one without
 *  reading the sentence that says so.
 *
 *  A crop with no photograph yet simply has none — an approximate picture of
 *  somebody else's crop would be worse than a card without one.
 */
const STANDING: Record<string, string> = {
  maize: '/field/maize.webp',
}

/** The bare field after the crop comes off: ploughed-under stubble. */
const HARVESTED = '/field/harvested.webp'

export function fieldPhoto(farm: { crop: string; status?: string }): string | null {
  if (farm.status === 'fallow') return HARVESTED
  return STANDING[farm.crop] ?? null
}
