/** Downscale on the phone before upload: field networks are slow and the model
 *  only needs ~300 px anyway. A 12 MP camera file is 3-5 MB; this sends a
 *  ~1280 px JPEG of a couple of hundred KB, which a 2G/3G line can carry
 *  inside the upload timeout. Falls back to the original if the browser cannot
 *  decode or re-encode it. */
export async function shrink(file: Blob, max = 1280): Promise<Blob> {
  // Any failure — a HEIC Chrome cannot decode, a corrupt file, an old iOS
  // without createImageBitmap — sends the photo as it is rather than none.
  try {
    const bmp = await createImageBitmap(file)
    const scale = Math.min(1, max / Math.max(bmp.width, bmp.height))
    const c = document.createElement('canvas')
    c.width = Math.round(bmp.width * scale)
    c.height = Math.round(bmp.height * scale)
    c.getContext('2d')!.drawImage(bmp, 0, 0, c.width, c.height)
    bmp.close?.()
    return await new Promise((res) => c.toBlob((b) => res(b ?? file), 'image/jpeg', 0.88))
  } catch {
    return file
  }
}
