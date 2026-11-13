/* AnnRakshak service worker: the app offline, and Web Push notifications.
 *
 * Offline matters here more than it does in most apps. The farmer opening this
 * is standing in a field at the edge of a cell, and before today a tap with no
 * signal gave them the browser's dinosaur — not the app saying it cannot reach
 * the server, which is a different and much better message. The shell is now
 * cached, so the app opens, finds its own last data, and says what it knows.
 *
 * What is never cached: /api (a farmer's own data and the answer to a photo —
 * it must be the live one or an honest failure), /media (their photographs),
 * and the sample images, which are large and only for a demo.
 */

const SHELL = 'annrakshak-shell-v1'
const KEEP = [SHELL]
const PRECACHE = ['/', '/index.html', '/manifest.webmanifest',
                  '/icon-192.png', '/icon-512.png', '/favicon-64.png']
const NEVER = ['/api/', '/media/', '/samples', '/health']

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(SHELL)
    // One missing icon must not fail the whole install, so each is its own try.
    await Promise.all(PRECACHE.map((url) => cache.add(url).catch(() => undefined)))
    await self.skipWaiting()
  })())
})

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const old = (await caches.keys()).filter((k) => k.startsWith('annrakshak-') && !KEEP.includes(k))
    await Promise.all(old.map((k) => caches.delete(k)))
    await self.clients.claim()
  })())
})

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return
  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return
  if (NEVER.some((p) => url.pathname.startsWith(p))) return

  // A page: the network decides, because a deploy must reach this phone. With
  // no network, the cached shell — the app's own router then draws the screen
  // and its own code says what it cannot reach.
  if (request.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        const fresh = await fetch(request)
        const cache = await caches.open(SHELL)
        cache.put('/index.html', fresh.clone()).catch(() => undefined)
        return fresh
      } catch {
        return (await caches.match('/index.html')) || Response.error()
      }
    })())
    return
  }

  // Everything else under /assets is content-hashed by the build: the name
  // changes when the file does, so the cached copy is never the wrong one.
  event.respondWith((async () => {
    const hit = await caches.match(request)
    if (hit) return hit
    const fresh = await fetch(request)
    if (fresh.ok && (url.pathname.startsWith('/assets/') || PRECACHE.includes(url.pathname))) {
      const cache = await caches.open(SHELL)
      cache.put(request, fresh.clone()).catch(() => undefined)
    }
    return fresh
  })())
})

self.addEventListener('push', (event) => {
  let data = {}
  try {
    data = event.data ? event.data.json() : {}
  } catch {
    data = { title: 'AnnRakshak', body: event.data ? event.data.text() : '' }
  }
  event.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    const visible = wins.some((w) => w.visibilityState === 'visible')
    if (visible && data.tag !== 'test') return
    await self.registration.showNotification(data.title || 'AnnRakshak', {
      body: data.body || '',
      icon: '/icon-192.png',
      badge: '/favicon-64.png',
      tag: data.tag || undefined,
      renotify: data.severity === 'warning',
      requireInteraction: data.severity === 'warning',
      data: { url: data.url || '/app' },
    })
  })())
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = (event.notification.data && event.notification.data.url) || '/app'
  event.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    for (const w of wins) {
      if (new URL(w.url).origin === self.location.origin) {
        await w.focus()
        w.navigate(url)
        return
      }
    }
    await self.clients.openWindow(url)
  })())
})

/* Photographs waiting for signal (src/lib/outbox.ts keeps them; the names and
 * rules here must match it). A farmer who took a photo with no signal and
 * closed the app still gets it sent: the browser wakes this worker when the
 * connection is back, and the answer arrives as a notification. */
const OUTBOX_DB = 'annrakshak'
const OUTBOX_STORE = 'outbox'
const OUTBOX_TAG = 'ar-outbox'
const OUTBOX_KEEP_MS = 3 * 24 * 3600 * 1000
const OUTBOX_LEASE_MS = 120000

function outboxReq(req) {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

function outboxOpen() {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open(OUTBOX_DB, 1)
    r.onupgradeneeded = () => {
      if (!r.result.objectStoreNames.contains(OUTBOX_STORE)) r.result.createObjectStore(OUTBOX_STORE, { keyPath: 'id' })
    }
    r.onsuccess = () => resolve(r.result)
    r.onerror = () => reject(r.error)
  })
}

async function outboxStore(mode) {
  return (await outboxOpen()).transaction(OUTBOX_STORE, mode).objectStore(OUTBOX_STORE)
}

/* Read and write in one transaction, so this worker and an open app cannot
 * both find the lease free and send the same photo twice. */
async function outboxClaim(id) {
  const s = await outboxStore('readwrite')
  const q = await outboxReq(s.get(id))
  if (!q || q.lease > Date.now()) return null
  q.lease = Date.now() + OUTBOX_LEASE_MS
  await outboxReq(s.put(q))
  return q
}

async function outboxSend() {
  const all = await outboxReq((await outboxStore('readonly')).getAll())
  all.sort((a, b) => a.at - b.at)
  for (const item of all) {
    if (Date.now() - item.at >= OUTBOX_KEEP_MS) {
      await outboxReq((await outboxStore('readwrite')).delete(item.id))
      continue
    }
    const q = await outboxClaim(item.id)
    if (!q) continue
    const fd = new FormData()
    fd.append('image', q.blob, 'photo.jpg')
    fd.append('lang', q.lang)
    fd.append('client_ref', q.id)
    let res
    try {
      res = await fetch(`/api/farms/${q.farmId}/diagnose`, { method: 'POST', body: fd, credentials: 'include' })
    } catch (e) {
      // Still no connection: give the lease back and let the browser try again.
      q.lease = 0
      q.tries = (q.tries || 0) + 1
      await outboxReq((await outboxStore('readwrite')).put(q))
      throw e
    }
    if (res.ok) {
      const result = await res.json().catch(() => null)
      await outboxReq((await outboxStore('readwrite')).delete(q.id))
      const sent = { id: q.id, farmId: q.farmId, result }
      const wins = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      wins.forEach((w) => w.postMessage({ type: 'outbox-sent', sent }))
      if (!wins.some((w) => w.visibilityState === 'visible') && result && result.problem_id) {
        await self.registration.showNotification(result.message || 'AnnRakshak', {
          body: '', icon: '/icon-192.png', badge: '/favicon-64.png', tag: `outbox-${q.id}`,
          data: { url: `/app/history/${result.problem_id}` },
        })
      }
    } else if (res.status === 408 || res.status === 429 || res.status >= 500) {
      q.lease = 0
      q.tries = (q.tries || 0) + 1
      await outboxReq((await outboxStore('readwrite')).put(q))
      throw new Error(`server ${res.status}`)   // the browser retries the sync later
    } else {
      // Refused for good (signed out, field deleted): sending again changes nothing.
      await outboxReq((await outboxStore('readwrite')).delete(q.id))
    }
  }
}

self.addEventListener('sync', (event) => {
  if (event.tag === OUTBOX_TAG) event.waitUntil(outboxSend())
})
