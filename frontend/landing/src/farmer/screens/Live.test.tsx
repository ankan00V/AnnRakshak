import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import type { Farm, Home } from '../../api/types'
import { clearCache } from '../../lib/hooks'
import { FarmerProvider } from '../FarmerContext'
import Live from './Live'

// The phone half of the flagship: a camera walk over a socket that drops,
// comes back, and must never let one connection's trouble land on another.
// The socket is a fake the test drives message by message; everything else on
// the screen is the real thing.

vi.mock('../../api/client', async (orig) => {
  const real = await orig<typeof import('../../api/client')>()
  return {
    ...real,
    api: {
      ...real.api,
      farms: async () => [{ id: 7, read_only: false }] as Farm[],
      home: async () => ({ farm: { id: 7, photo_diagnosis: true }, problems: [] }) as unknown as Home,
      // No voice in a test: the speaker falls back to silence.
      tts: async () => { throw new Error('no voice here') },
    },
  }
})

type Msg = Record<string, unknown>

class FakeSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3
  static all: FakeSocket[] = []
  readyState = 0
  sent: Msg[] = []
  onopen: (() => void) | null = null
  onmessage: ((e: MessageEvent) => void) | null = null
  onclose: (() => void) | null = null
  url: string
  constructor(url: string) {
    this.url = url
    FakeSocket.all.push(this)
  }
  send(d: string) { this.sent.push(JSON.parse(d)) }
  /** What the page asks for. A real browser reports the close later, on its
   *  own; the test decides when that happens, with `drop`. */
  close() { this.readyState = 3 }
  open() { act(() => { this.readyState = 1; this.onopen?.() }) }
  receive(m: Msg) { act(() => { this.onmessage?.({ data: JSON.stringify(m) } as MessageEvent) }) }
  /** The line goes, or a close the page asked for earlier is finally reported. */
  drop() { act(() => { this.readyState = 3; this.onclose?.() }) }
  frames() { return this.sent.filter((m) => m.type === 'frame').length }
}

const CONTEXT = {
  location: { lat: 21.17, lon: 79.65, source: 'farm', accuracy_m: null, km_from_farm: 0, far_from_farm: false },
  weather_now: { temp_c: 28, rh_pct: 70 }, forecast: null, soil: { ph: null, moisture: null },
  crop: { id: 'rice', name: 'Rice', stage: 'tillering', stage_name: 'Tillering', das: 40, photo_model: true },
  risks: [],
}
const ready = (token: string, resumed = false): Msg => ({
  type: 'ready', context: CONTEXT, photo_model: true, resume: token, resumed,
  guide: { step: 'leaf_top', kind: 'close', index: 2, total: 6, need: 4, got: 1, text: 'Show the top of a leaf.' },
})

const restore: (() => void)[] = []
let cameraEnded: () => void = () => undefined
function stub(target: object, key: string, desc: PropertyDescriptor) {
  const before = Object.getOwnPropertyDescriptor(target, key)
  Object.defineProperty(target, key, { configurable: true, ...desc })
  restore.push(() => (before ? Object.defineProperty(target, key, before) : delete (target as Record<string, unknown>)[key]))
}

beforeEach(() => {
  FakeSocket.all = []
  clearCache()
  localStorage.setItem('ar.farm', '7')
  vi.stubGlobal('WebSocket', FakeSocket)
  // A phone: a coarse pointer and a camera.
  vi.stubGlobal('matchMedia', (q: string) => ({
    matches: q === '(pointer: coarse)', media: q, addEventListener() {}, removeEventListener() {},
  }))
  const track = {
    stop() {}, getCapabilities: () => ({}),
    addEventListener(name: string, fn: () => void) { if (name === 'ended') cameraEnded = fn },
  }
  const stream = { getTracks: () => [track], getVideoTracks: () => [track] }
  stub(navigator, 'mediaDevices', { value: { getUserMedia: async () => stream } })
  stub(navigator, 'geolocation', { value: undefined })
  // A camera preview with a picture in it, and a canvas that can cut a frame.
  stub(HTMLMediaElement.prototype, 'readyState', { get: () => 4 })
  stub(HTMLMediaElement.prototype, 'play', { value: async () => undefined })
  stub(HTMLMediaElement.prototype, 'srcObject', { get: () => null, set() {} })
  stub(HTMLVideoElement.prototype, 'videoWidth', { get: () => 640 })
  stub(HTMLVideoElement.prototype, 'videoHeight', { get: () => 480 })
  stub(HTMLCanvasElement.prototype, 'getContext', { value: () => ({ drawImage() {} }) })
  stub(HTMLCanvasElement.prototype, 'toDataURL', { value: () => 'data:image/jpeg;base64,QUJD' })
})

afterEach(() => {
  vi.unstubAllGlobals()
  while (restore.length) restore.pop()!()
})

async function startCall(): Promise<FakeSocket> {
  render(<MemoryRouter><FarmerProvider><Live /></FarmerProvider></MemoryRouter>)
  const before = FakeSocket.all.length
  await userEvent.click(await screen.findByRole('button', { name: /start live check/i }))
  await waitFor(() => expect(FakeSocket.all.length).toBe(before + 1))
  const ws = FakeSocket.all.at(-1)!
  ws.open()
  expect(ws.sent[0]).toMatchObject({ type: 'start', mode: 'walk' })
  return ws
}

const pause = (ms: number) => act(() => new Promise((r) => setTimeout(r, ms)))

describe('the live call on a phone', () => {
  it('sends frames while the farmer is walking', async () => {
    const ws = await startCall()
    ws.receive(ready('t1'))
    await waitFor(() => expect(ws.frames()).toBeGreaterThan(0))
  })

  it('does not let a connection it has given up on end the next call', async () => {
    // A "call dropped" screen used to leave its socket open, and the server
    // only lets an idle one go ninety seconds later. When that close finally
    // arrived it landed on whatever call the farmer had started since, and
    // set that one redialling over the top of their walk.
    const first = await startCall()
    first.receive(ready('t1'))
    first.receive({ type: 'error', code: 'RESUME_UNKNOWN' })   // the walk is gone
    expect(await screen.findByText(/call with the AI dropped/i)).toBeInTheDocument()
    expect(first.readyState).toBe(3)   // and the line it was on is hung up

    await userEvent.click(screen.getByRole('button', { name: /start live check/i }))
    await waitFor(() => expect(FakeSocket.all.length).toBe(2))
    const second = FakeSocket.all[1]
    second.open()
    second.receive(ready('t2'))

    first.drop()                       // the old line's close, arriving late
    await pause(1200)                  // longer than the first redial wait
    expect(screen.queryByText(/line dropped/i)).not.toBeInTheDocument()
    expect(FakeSocket.all.length).toBe(2)
    expect(second.frames()).toBeGreaterThan(0)
  })

  it('keeps the question on screen when the line drops while it is being read', async () => {
    // Every view is in, and the look-alike question is up. The line drops and
    // comes back. Sending frames again made the server announce the walk done
    // a second time — and that second "done" finished the call underneath the
    // question, throwing the farmer's answer away.
    const ws = await startCall()
    ws.receive(ready('t1'))
    await waitFor(() => expect(ws.frames()).toBeGreaterThan(0))
    ws.receive({
      type: 'ask', cue_id: 'cue1', question: 'Are the spots shaped like an eye?',
      candidates: [{ id: 'a', name: 'Blast', signature: 'eye-shaped' }, { id: 'b', name: 'Brown spot', signature: 'round' }],
    })
    ws.receive({ type: 'steps_done', asked: true })
    ws.drop()

    expect(await screen.findByText(/line dropped/i)).toBeInTheDocument()
    await waitFor(() => expect(FakeSocket.all.length).toBe(2), { timeout: 2000 })
    const back = FakeSocket.all[1]
    back.open()
    expect(back.sent[0]).toEqual({ type: 'resume', token: 't1' })
    back.receive(ready('t2', true))

    await pause(800)
    expect(back.frames()).toBe(0)
    expect(back.sent.some((m) => m.type === 'finish')).toBe(false)
    expect(screen.getByText('Are the spots shaped like an eye?')).toBeInTheDocument()

    // And the answer, when it comes, is the one that finishes the walk.
    await userEvent.click(screen.getByRole('button', { name: /^yes$/i }))
    expect(back.sent.filter((m) => m.type !== 'ping').slice(-2)).toEqual([
      { type: 'answer', cue_id: 'cue1', answer: 'yes' },
      { type: 'finish', send_to_expert: false },
    ])
  })

  it('ends the call when another app takes the camera, instead of redialling into a black screen', async () => {
    // An incoming phone call takes the camera. The line was closed as part of
    // stopping, the close was read as a dropped line, and the call redialled
    // back into "live" with no picture and a voice still giving directions.
    const ws = await startCall()
    ws.receive(ready('t1'))
    act(() => cameraEnded())
    expect(await screen.findByText(/another app is using the camera/i)).toBeInTheDocument()
    ws.drop()                          // the close it asked for, reported
    await pause(1200)
    expect(FakeSocket.all.length).toBe(1)
    expect(screen.queryByText(/line dropped/i)).not.toBeInTheDocument()
    expect(screen.getByText(/another app is using the camera/i)).toBeInTheDocument()
  })

  it('does not send the next frame on a late reply to an earlier one', async () => {
    // Only the reply to the frame in flight frees the next one. A late reply
    // used to, so two frames rode at once on exactly the links that were
    // struggling, and the link was never timed again.
    const ws = await startCall()
    ws.receive(ready('t1'))
    await waitFor(() => expect(ws.frames()).toBe(1))
    const reply = (seq: number) => ({
      type: 'frame', seq, quality: { ok: true, hint: null, hint_text: null, sharp: 50, bright: 120, veg: 0.6 },
      counted: true, advanced: false, live: null,
      guide: { step: 'leaf_top', kind: 'close', index: 2, total: 6, need: 4, got: 2, text: 'Show the top of a leaf.' },
    })
    ws.receive(reply(0))               // an answer to something older
    await pause(900)
    expect(ws.frames()).toBe(1)
    ws.receive(reply(1))               // the answer to the frame in flight
    await waitFor(() => expect(ws.frames()).toBe(2))
  })
})
