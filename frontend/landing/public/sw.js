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
