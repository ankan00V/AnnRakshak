import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// The @font-face rules first, so they ride in the one hashed stylesheet rather
// than being a second, unhashed, render-blocking request (see the file's note).
import './fonts.css'
import './index.css'
import App from './App.tsx'
import { loadLocale, savedLang } from './lib/i18n'
import ErrorBoundary from './ui/ErrorBoundary'

/** Every language but English is its own chunk. Fetching it before the first
 *  render means a Hindi farmer's Home is drawn in Hindi, not in English and
 *  then again in Hindi a moment later. A slow link must not hold the screen
 *  blank, though: past ~1.5 s we draw anyway, and FarmerContext redraws when
 *  the strings land (the same load, shared). */
async function boot() {
  const lang = savedLang()
  if (lang !== 'en') {
    await Promise.race([
      loadLocale(lang).catch(() => false),
      new Promise((r) => setTimeout(r, 1500)),
    ])
  }
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </StrictMode>,
  )
}

/** Hand the service worker what this page loaded before the worker existed
 *  (see 'message' in public/sw.js): the language table, the script font, the
 *  photographs. Without it the first visit's files are fetched again the first
 *  time the farmer is offline, which is to say not at all. Waits for the
 *  worker FarmerApp registers; on a page that never registers one, never runs. */
function shareFirstLoad() {
  if (!('serviceWorker' in navigator)) return
  void navigator.serviceWorker.ready.then((reg) => {
    const send = () => {
      const urls = performance.getEntriesByType('resource')
        .map((e) => e.name)
        .filter((u) => u.startsWith(location.origin))
      reg.active?.postMessage({ type: 'precache', urls })
    }
    if (document.readyState === 'complete') send()
    else window.addEventListener('load', send, { once: true })
  }).catch(() => undefined)
}

void boot()
shareFirstLoad()
