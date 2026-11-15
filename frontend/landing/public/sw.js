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

// Written by the build (vite.config.ts, precache()): a hash of the files, what
// opening the app needs (REQUIRED), and what is good to have offline
// (OPTIONAL). In `vite dev` they stay as they are here.
const BUILD = 'dev' // __AR_BUILD__
const REQUIRED = [] // __AR_REQUIRED__
const OPTIONAL = [] // __AR_OPTIONAL__
const ASSETS = REQUIRED.concat(OPTIONAL)

// One cache per build: a deploy names a new one, and activate deletes the old,
// so a phone does not carry every past version of the app in its storage.
const SHELL = `annrakshak-${BUILD}`
const NEVER = ['/api/', '/media/', '/samples', '/health']
// Kept the first time they are fetched, then served from here: content-hashed
// bundles, and the fonts and photographs, which keep their names. The farmer's
// own script font (Devanagari, Tamil...) arrives this way, since which one it
// is depends on the farmer.
const KEEP = ['/assets/', '/fonts/', '/photos/', '/field/', '/brand/']
// How long a page load waits on the network before the cached app is shown.
// On a dying 2G link a fetch can hang for a minute; the farmer should see their
// app in three seconds and get the fresh copy next time.
const NAV_TIMEOUT_MS = 3000

const keepable = (path) => KEEP.some((p) => path.startsWith(p))

async function putAll(cache, urls) {
  // One missing file must not fail the whole install, so each is its own try.
  await Promise.all(urls.map(async (url) => {
    if (await cache.match(url, { ignoreVary: true })) return
    await cache.add(url).catch(() => undefined)
  }))
}

// A content-hashed bundle: its name is its content, so any copy of it is this file.
const hashed = (path) => path.startsWith('/assets/')

/* What the install asks the network for. Everything but the bundles keeps its
 * name across deploys, and the browser's HTTP cache may hold an older copy (a
 * font or photo for a week): 'reload' goes to the server. A bundle cannot be
 * stale, and the page has usually just loaded it, so it may come from the
 * HTTP cache: asking again would spend 2G on bytes the phone already has. */
const installRequest = (path) => new Request(path, { cache: hashed(path) ? 'default' : 'reload' })

/** Copies into `cache` each bundle an older build already kept, and returns
 *  what is left to fetch: a deploy that changed one screen then costs that
 *  screen's bytes, not the whole app's again. */
async function reuse(cache, paths) {
  const left = []
  for (const path of paths) {
    if (await cache.match(path, { ignoreVary: true })) continue
    const old = hashed(path) ? await caches.match(path, { ignoreVary: true }) : undefined
    if (old) await cache.put(path, old)
    else left.push(path)
  }
  return left
}

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(SHELL)
    // What opening the app needs. addAll rejects if any one file fails, and
    // that fails the install: the worker already here, and its complete
    // cache, stay in charge, and the next visit tries again. Installing past
    // a failure here would let activate delete a whole app for half of one.
    await cache.addAll((await reuse(cache, REQUIRED)).map(installRequest))
    // The other screens, the fonts, the photographs: best effort. A screen
    // missing offline says it needs signal; the app still opens.
    await Promise.all((await reuse(cache, OPTIONAL)).map((path) =>
      cache.add(installRequest(path)).catch(() => undefined)))
    await self.skipWaiting()
  })())
})

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const old = (await caches.keys()).filter((k) => k.startsWith('annrakshak-') && k !== SHELL)
    await Promise.all(old.map((k) => caches.delete(k)))
    await self.clients.claim()
  })())
})

/* The page that registered this worker loaded its first files before the
 * worker existed, so the worker never saw them: the farmer's language table
 * and script font above all. main.tsx sends their addresses once the worker is
 * ready, and they are kept like anything else fetched through it. */
self.addEventListener('message', (event) => {
  const msg = event.data
  if (!msg || msg.type !== 'precache' || !Array.isArray(msg.urls)) return
  const urls = msg.urls
    .map((u) => { try { return new URL(u, self.location.origin) } catch { return null } })
    .filter((u) => u && u.origin === self.location.origin && keepable(u.pathname))
    .map((u) => u.pathname)
  if (urls.length) event.waitUntil((async () => putAll(await caches.open(SHELL), urls))())
})

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return
  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return
  if (NEVER.some((p) => url.pathname.startsWith(p))) return

  // A page: the network first, because a deploy must reach this phone — but
  // not for ever. Past NAV_TIMEOUT_MS, or with no network, the cached shell;
  // the app's own router then draws the screen and its own code says what it
  // cannot reach.
  //
  // The page the network returns is never written into the cache. After a
  // deploy it is the new build's shell, naming bundles this worker's cache
  // does not have: kept here, it would open offline as a blank page. The
  // offline shell is the /index.html this worker installed with its own
  // bundles; the next build's worker installs its own.
  if (request.mode === 'navigate') {
    event.respondWith((async () => {
      const cache = await caches.open(SHELL)
      const network = fetch(request)
      event.waitUntil(network.catch(() => undefined))
      const first = await Promise.race([
        network.catch(() => null),
        new Promise((r) => setTimeout(r, NAV_TIMEOUT_MS, null)),
      ])
      if (first && first.ok) return first
      const cached = await cache.match('/index.html', { ignoreVary: true })
      if (cached) return cached
      // Nothing kept yet (the very first visit): whatever the network says.
      return first || network.catch(() => Response.error())
    })())
    return
  }

  if (!keepable(url.pathname) && !ASSETS.includes(url.pathname)) return
  event.respondWith((async () => {
    // ignoreVary: the server marks some files Vary: Origin (its CORS layer
    // does that for any request that carried an Origin). A module script
    // carries one and the copy kept at install did not, so without this the
    // lookup missed and a screen kept for offline asked the network for its
    // own icons — and, offline, failed to open. Nothing kept here differs by
    // origin: it is all this site's own files.
    const hit = await caches.match(request, { ignoreVary: true })
    if (hit) return hit
    // A font or photo keeps its name when it is replaced, and the browser's own
    // cache holds it for a week; ask the server (a 304 is cheap) so a new build
    // does not store last week's copy. Hashed bundles cannot be stale.
    const fresh = await fetch(hashed(url.pathname) ? request : new Request(request, { cache: 'no-cache' }))
    // Only a whole, good file: a 404 kept here would be served for ever, and a
    // 206 is a piece of one.
    if (fresh.status === 200) {
      const cache = await caches.open(SHELL)
      event.waitUntil(cache.put(request, fresh.clone()).catch(() => undefined))
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
