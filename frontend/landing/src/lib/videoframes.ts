/** Still frames out of a video file the farmer already filmed.
 *
 *  The live field walk wants a camera it can point at a plant. A laptop has one,
 *  but it faces the person, not the crop, so on a computer the same check runs
 *  on a video instead: we step through the file, hand each frame to the server
 *  as if it had just come off a phone camera, and the server cannot tell the
 *  difference. Decoding happens here, in the browser — the video itself is never
 *  uploaded.
 *
 *  Only the browser's own decoders are used, so a file it cannot play (HEVC on
 *  some desktops) fails at `open` with a clear reason rather than silently
 *  handing back blank frames.
 */

export const MAX_VIDEO_BYTES = 200 * 1024 * 1024
export const MAX_VIDEO_SECONDS = 180

export type VideoReason = 'not_video' | 'too_big' | 'unreadable' | 'too_long'

export class VideoError extends Error {
  reason: VideoReason
  constructor(reason: VideoReason) {
    super(reason)
    this.reason = reason
  }
}

export type Grabber = {
  /** Seconds of the file we will walk through (capped at MAX_VIDEO_SECONDS). */
  readonly duration: number
  /** The file's own length, so a screen can say when it watched only part of it. */
  readonly full: number
  /** A JPEG of the frame at `at` seconds, base64 without the data: prefix. */
  grab(at: number): Promise<string | null>
  close(): void
}

const SEEK_TIMEOUT_MS = 4000

/** Seek `v` to `at` and resolve once a frame for that position is drawable.
 *  A seek to where we already are fires no `seeked` event, and a broken
 *  position fires none either, so both are answered by the timeout. */
function seek(v: HTMLVideoElement, at: number): Promise<void> {
  if (Math.abs(v.currentTime - at) < 0.001 && v.readyState >= 2) return Promise.resolve()
  return new Promise((resolve) => {
    let timer = 0
    const done = () => {
      window.clearTimeout(timer)
      v.removeEventListener('seeked', done)
      resolve()
    }
    timer = window.setTimeout(done, SEEK_TIMEOUT_MS)
    v.addEventListener('seeked', done)
    try {
      v.currentTime = at
    } catch {
      done()  // some decoders refuse a seek outside what they have parsed
    }
  })
}

function metadata(v: HTMLVideoElement): Promise<void> {
  if (v.readyState >= 1) return Promise.resolve()
  return new Promise((resolve, reject) => {
    const ok = () => { off(); resolve() }
    const bad = () => { off(); reject(new VideoError('unreadable')) }
    const off = () => {
      window.clearTimeout(timer)
      v.removeEventListener('loadedmetadata', ok)
      v.removeEventListener('error', bad)
    }
    const timer = window.setTimeout(bad, 20000)
    v.addEventListener('loadedmetadata', ok)
    v.addEventListener('error', bad)
  })
}

/** Open `file` in `v` — the same element the screen is showing, so the farmer
 *  watches the frame that is being looked at — and return a frame grabber.
 *  `maxSide` and `quality` match what the live camera path sends. */
export async function openVideo(file: File, v: HTMLVideoElement,
                                maxSide: number, quality: number): Promise<Grabber> {
  if (!file.type.startsWith('video/')) throw new VideoError('not_video')
  if (file.size > MAX_VIDEO_BYTES) throw new VideoError('too_big')

  const url = URL.createObjectURL(file)
  const canvas = document.createElement('canvas')
  let closed = false
  const close = () => {
    if (closed) return
    closed = true
    // The element is shared. A file abandoned while it was still opening is
    // closed after the next one has been put in it — and clearing the element
    // then emptied the farmer's new video, which was read as unreadable.
    if (v.src === url) {
      v.removeAttribute('src')
      v.load()
    }
    URL.revokeObjectURL(url)
  }

  v.srcObject = null
  v.muted = true
  v.playsInline = true
  v.preload = 'auto'
  v.src = url
  try {
    await metadata(v)
  } catch (e) {
    close()
    throw e
  }
  const full = v.duration
  if (!Number.isFinite(full) || full <= 0 || !v.videoWidth || !v.videoHeight) {
    close()
    throw new VideoError('unreadable')
  }

  const duration = Math.min(full, MAX_VIDEO_SECONDS)

  const grab = async (at: number): Promise<string | null> => {
    if (closed) return null
    await seek(v, Math.max(0, Math.min(at, duration)))
    if (closed || v.readyState < 2 || !v.videoWidth) return null
    const scale = Math.min(1, maxSide / Math.max(v.videoWidth, v.videoHeight))
    canvas.width = Math.round(v.videoWidth * scale)
    canvas.height = Math.round(v.videoHeight * scale)
    const ctx = canvas.getContext('2d')
    if (!ctx) return null
    ctx.drawImage(v, 0, 0, canvas.width, canvas.height)
    try {
      return canvas.toDataURL('image/jpeg', quality).split(',')[1] || null
    } catch {
      return null  // a tainted canvas should be impossible for a local file
    }
  }

  return { duration, full, grab, close }
}
