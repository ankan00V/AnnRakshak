/* AnnRakshak service worker: Web Push notifications.
 * A push shows a system notification only when no AnnRakshak window is visible —
 * an open app already shows the same notice itself (Server-Sent Events). */

self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()))

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
