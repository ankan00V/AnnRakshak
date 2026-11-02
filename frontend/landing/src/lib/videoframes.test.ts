import { describe, expect, it } from 'vitest'
import { MAX_VIDEO_BYTES, VideoError, openVideo } from './videoframes'

/** Only the checks that run before the browser is asked to decode anything:
 *  happy-dom has no video decoder, so the frame grabbing itself is exercised in
 *  the browser instead. */
const file = (type: string, size: number) => ({ type, size }) as File

describe('openVideo', () => {
  it('turns a photo away before touching the video element', async () => {
    const el = document.createElement('video')
    await expect(openVideo(file('image/jpeg', 1000), el, 512, 0.72)).rejects.toMatchObject({ reason: 'not_video' })
    expect(el.getAttribute('src')).toBe(null)
  })

  it('refuses a file too big to walk through', async () => {
    const el = document.createElement('video')
    const e = await openVideo(file('video/mp4', MAX_VIDEO_BYTES + 1), el, 512, 0.72).catch((x) => x)
    expect(e).toBeInstanceOf(VideoError)
    expect(e.reason).toBe('too_big')
  })
})
