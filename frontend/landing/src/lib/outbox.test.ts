import type { DiagnoseResult } from '../api/types'
import { EVENT, KEEP_MS, LEASE_MS, flush, inMemory, keepAfter, pendingPhotos, queuePhoto, setStore, type OutboxChange, type Queued } from './outbox'

// A photograph taken where the signal gives out must survive until there is
// signal again, be sent exactly once, and stop being kept when the server has
// refused it for good or it has grown too old to describe the field.

const photo = () => new Blob(['jpeg'], { type: 'image/jpeg' })
const answer = (id: number) => ({ problem_id: id, message: 'Rice blast' }) as unknown as DiagnoseResult
const offline = () => Object.assign(new Error('offline'), { status: 0 })
const refused = (status: number) => Object.assign(new Error('refused'), { status })

beforeEach(() => setStore(inMemory()))
afterEach(() => setStore(null))

describe('photos waiting for signal', () => {
  it('keeps a photo and sends it once the connection is back', async () => {
    await queuePhoto(7, photo(), 'mr', 'p1')
    expect((await pendingPhotos(7)).map((q) => q.id)).toEqual(['p1'])

    const send = vi.fn(async (q: Queued) => answer(q.farmId))
    const sent = await flush(send)
    expect(send).toHaveBeenCalledTimes(1)
    expect(send.mock.calls[0][0]).toMatchObject({ id: 'p1', farmId: 7, lang: 'mr' })
    expect(sent.map((s) => s.result.problem_id)).toEqual([7])
    expect(await pendingPhotos()).toEqual([])
  })

  it('stops at the first sign there is still no signal, and keeps every photo', async () => {
    await queuePhoto(7, photo(), 'en', 'a')
    await queuePhoto(7, photo(), 'en', 'b')
    const send = vi.fn(async () => { throw offline() })
    expect(await flush(send)).toEqual([])
    expect(send).toHaveBeenCalledTimes(1)          // did not fail the second one too
    const left = await pendingPhotos()
    expect(left.map((q) => [q.id, q.tries, q.lease])).toEqual([['a', 1, 0], ['b', 0, 0]])
  })

  it('drops a photo the server refused for good, and keeps one it was only too busy for', async () => {
    await queuePhoto(7, photo(), 'en', 'gone')
    await queuePhoto(7, photo(), 'en', 'busy')
    await flush(async (q) => { throw refused(q.id === 'gone' ? 404 : 503) })
    expect((await pendingPhotos()).map((q) => q.id)).toEqual(['busy'])
    expect([0, 408, 429, 500, 503].every((s) => keepAfter({ status: s }))).toBe(true)
    expect([400, 401, 403, 404, 413, 422].some((s) => keepAfter({ status: s }))).toBe(false)
  })

  it('never sends the same photo twice when two senders run at once', async () => {
    // The open app and the service worker can both wake up on the same
    // reconnection. The lease is what keeps one plant from becoming two cases.
    await queuePhoto(7, photo(), 'en', 'once')
    let release: () => void = () => undefined
    const slow = vi.fn((q: Queued) => new Promise<DiagnoseResult>((r) => { release = () => r(answer(q.farmId)) }))
    const first = flush(slow)
    const second = flush(slow)                      // the same flight, not a second one
    expect(second).toBe(first)
    await vi.waitFor(() => expect(slow).toHaveBeenCalledTimes(1))
    release()
    await first
    expect(slow).toHaveBeenCalledTimes(1)
  })

  it('gives a photo to one sender at a time, and back if that sender went quiet', async () => {
    // The app and the service worker share the store, not a flight: the lease
    // in the record is what decides which of them may send.
    const store = inMemory()
    setStore(store)
    await queuePhoto(7, photo(), 'en', 'leased')
    const now = Date.now()
    expect(await store.claim('leased', now)).toBe(true)
    expect(await store.claim('leased', now + 1000)).toBe(false)          // the other sender
    expect(await store.claim('leased', now + LEASE_MS + 1)).toBe(true)   // the first one died mid-send
    expect(await store.claim('missing', now)).toBe(false)
  })

  it('lets go of a photo too old to describe the field', async () => {
    const q = await queuePhoto(7, photo(), 'en', 'old')
    const store = inMemory()
    setStore(store)
    await store.put({ ...q, at: Date.now() - KEEP_MS - 1 })
    const send = vi.fn(async () => answer(7))
    await flush(send)
    expect(send).not.toHaveBeenCalled()
    expect(await pendingPhotos()).toEqual([])
  })

  it('tells the screen how many are waiting and when one was answered', async () => {
    const seen: OutboxChange[] = []
    const on = (e: Event) => seen.push((e as CustomEvent<OutboxChange>).detail)
    window.addEventListener(EVENT, on)
    try {
      await queuePhoto(7, photo(), 'en', 'x')
      await vi.waitFor(() => expect(seen.at(-1)?.pending).toBe(1))
      await flush(async () => answer(42))
      await vi.waitFor(() => expect(seen.some((c) => c.sent?.result.problem_id === 42 && c.pending === 0)).toBe(true))
    } finally {
      window.removeEventListener(EVENT, on)
    }
  })
})
