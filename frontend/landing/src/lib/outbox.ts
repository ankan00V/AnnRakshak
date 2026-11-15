/** Photographs waiting for signal.
 *
 *  A farmer photographs a sick plant at the edge of the field, where the
 *  signal gives out. Before this the photo simply failed: the screen said it
 *  could not reach the server, and the picture — the one thing they walked out
 *  to get — was gone the moment they left the screen. Now it is kept on the
 *  phone and sent the moment there is a connection: when the app is next open
 *  and online, and, on phones whose browser supports it, by the service worker
 *  even with the app closed (public/sw.js reads this same store).
 *
 *  Kept for three days at most. A photo older than that describes a field that
 *  has moved on, and an answer about it would be about the wrong plant.
 *
 *  Each photo is sent once. The app and the service worker can both be
 *  running, so a photo is claimed with a short lease before it is sent; and it
 *  carries its own reference, so a send that reached the server but whose
 *  answer was lost is recognised there rather than diagnosed twice.
 */
import type { DiagnoseResult, Lang } from '../api/types'

export const DB_NAME = 'annrakshak'
export const STORE = 'outbox'
export const SYNC_TAG = 'ar-outbox'
export const KEEP_MS = 3 * 24 * 3600 * 1000
/** Longer than an upload on a slow link can take, so a slow send is not
 *  mistaken for a dead one and sent again. */
export const LEASE_MS = 120_000
export const EVENT = 'ar-outbox'

export type Queued = {
  id: string
  farmId: number
  lang: Lang
  blob: Blob
  at: number
  tries: number
  lease: number
}

export type Sent = { id: string; farmId: number; result: DiagnoseResult }
export type OutboxChange = { pending: number; sent?: Sent; dropped?: Queued }

/** Where the queue lives. IndexedDB on a phone; memory where there is none
 *  (a test, or a browser that refuses storage in private mode) — then a photo
 *  survives as long as the tab, which is still better than not at all. */
export interface Store {
  all(): Promise<Queued[]>
  put(q: Queued): Promise<void>
  del(id: string): Promise<void>
  /** Take the lease on `id` if nobody holds it; false if someone does. */
  claim(id: string, now: number): Promise<boolean>
}

function memoryStore(): Store {
  const items = new Map<string, Queued>()
  return {
    all: async () => [...items.values()].sort((a, b) => a.at - b.at),
    put: async (q) => { items.set(q.id, { ...q }) },
    del: async (id) => { items.delete(id) },
    claim: async (id, now) => {
      const q = items.get(id)
      if (!q || q.lease > now) return false
      items.set(id, { ...q, lease: now + LEASE_MS })
      return true
    },
  }
}

function idb<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open(DB_NAME, 1)
    r.onupgradeneeded = () => {
      if (!r.result.objectStoreNames.contains(STORE)) r.result.createObjectStore(STORE, { keyPath: 'id' })
    }
    r.onsuccess = () => resolve(r.result)
    r.onerror = () => reject(r.error)
  })
}

function indexedStore(): Store {
  const tx = async (mode: IDBTransactionMode) => (await open()).transaction(STORE, mode).objectStore(STORE)
  return {
    all: async () => ((await idb((await tx('readonly')).getAll())) as Queued[]).sort((a, b) => a.at - b.at),
    put: async (q) => { await idb((await tx('readwrite')).put(q)) },
    del: async (id) => { await idb((await tx('readwrite')).delete(id)) },
    // Read and write in one transaction, so the app and the service worker
    // cannot both find the lease free.
    claim: async (id, now) => {
      const s = await tx('readwrite')
      const q = (await idb(s.get(id))) as Queued | undefined
      if (!q || q.lease > now) return false
      await idb(s.put({ ...q, lease: now + LEASE_MS }))
      return true
    },
  }
}

let store: Store | null = null
function current(): Store {
  if (!store) store = typeof indexedDB !== 'undefined' ? indexedStore() : memoryStore()
  return store
}

/** For tests, and nothing else. */
export function setStore(s: Store | null) {
  store = s
}
export const inMemory = memoryStore

function announce(change: Omit<OutboxChange, 'pending'>) {
  void pendingPhotos().then((p) => {
    window.dispatchEvent(new CustomEvent<OutboxChange>(EVENT, { detail: { pending: p.length, ...change } }))
  }).catch(() => undefined)
}

export function newId(): string {
  try {
    return crypto.randomUUID()
  } catch {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  }
}

/** Keep a photograph to send when there is signal. */
export async function queuePhoto(farmId: number, blob: Blob, lang: Lang, id = newId()): Promise<Queued> {
  const q: Queued = { id, farmId, lang, blob, at: Date.now(), tries: 0, lease: 0 }
  try {
    await current().put(q)
  } catch {
    // Storage refused (full, or private mode): keep it for this tab at least.
    store = memoryStore()
    await store.put(q)
  }
  announce({})
  void askForSync()
  return q
}

export async function pendingPhotos(farmId?: number): Promise<Queued[]> {
  const now = Date.now()
  const all = (await current().all()).filter((q) => now - q.at < KEEP_MS)
  return farmId == null ? all : all.filter((q) => q.farmId === farmId)
}

export type Send = (q: Queued) => Promise<DiagnoseResult>

/** Why a send failed, which decides whether the photo is kept. */
export function keepAfter(e: unknown): boolean {
  const status = (e as { status?: number })?.status
  // No connection, a timeout, the server busy or failing: try again later.
  if (status == null || status === 0 || status === 408 || status === 429 || status >= 500) return true
  // Refused for good (the field was deleted, the account signed out): sending
  // it again will not change the answer.
  return false
}

let flushing: Promise<Sent[]> | null = null

/** Send what is waiting, oldest first. One flush at a time; stops at the first
 *  sign that there is still no connection rather than failing every photo. */
export function flush(send: Send): Promise<Sent[]> {
  if (!flushing) {
    flushing = run(send).finally(() => { flushing = null })
  }
  return flushing
}

async function run(send: Send): Promise<Sent[]> {
  const s = current()
  const sent: Sent[] = []
  const now = Date.now()
  for (const q of await s.all()) {
    if (now - q.at >= KEEP_MS) {
      await s.del(q.id)
      announce({ dropped: q })
      continue
    }
    if (!(await s.claim(q.id, Date.now()))) continue
    try {
      const result = await send(q)
      await s.del(q.id)
      const done = { id: q.id, farmId: q.farmId, result }
      sent.push(done)
      announce({ sent: done })
    } catch (e) {
      if (keepAfter(e)) {
        await s.put({ ...q, tries: q.tries + 1, lease: 0 })
        if ((e as { status?: number })?.status === 0) break   // still offline: the rest would fail too
      } else {
        await s.del(q.id)
        announce({ dropped: q })
      }
    }
  }
  return sent
}

/** Ask the browser to wake the service worker when the connection is back,
 *  so the photo goes even if the app is closed. Not every browser can. */
export async function askForSync(): Promise<boolean> {
  try {
    const reg = await navigator.serviceWorker?.getRegistration('/')
    const sync = (reg as unknown as { sync?: { register(tag: string): Promise<void> } } | undefined)?.sync
    if (!sync) return false
    await sync.register(SYNC_TAG)
    return true
  } catch {
    return false
  }
}

/** Flush now, and again whenever the connection or the app comes back. */
export function startOutbox(send: Send): () => void {
  const go = () => {
    if (navigator.onLine !== false) void flush(send).catch(() => undefined)
  }
  const back = () => { if (document.visibilityState === 'visible') go() }
  // The service worker sends from the background; tell this tab when it has.
  const fromWorker = (ev: MessageEvent) => {
    if (ev.data?.type === 'outbox-sent') announce({ sent: ev.data.sent as Sent })
  }
  window.addEventListener('online', go)
  document.addEventListener('visibilitychange', back)
  navigator.serviceWorker?.addEventListener?.('message', fromWorker)
  const timer = window.setInterval(go, 60_000)
  go()
  return () => {
    window.removeEventListener('online', go)
    document.removeEventListener('visibilitychange', back)
    navigator.serviceWorker?.removeEventListener?.('message', fromWorker)
    window.clearInterval(timer)
  }
}
