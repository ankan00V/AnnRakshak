// App screens as an iPhone 15 shows them: 393 x 852 points at 3x, the status
// bar and home indicator in their places, and the app's own safe-area padding
// under them. Captured from the running app (launch config "landing-isolated"
// + "backend-isolated"), signed in as the demo farmer.
//
//   node capture.mjs   -> out/scan.png      the Scan screen
//                         out/result.png    a sample photo's answer (False smut)
//                         out/treat.png     the same answer, at what to do
//                         out/result-mr.png the answer, in Marathi
//   (each 1179 x 2556)
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import puppeteer from 'puppeteer-core'

const HERE = new URL('.', import.meta.url).pathname
const OUT = join(HERE, 'out'); mkdirSync(OUT, { recursive: true })
const BASE = process.env.BASE ?? 'https://localhost:5176'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const browser = await puppeteer.launch({
  headless: 'new',
  executablePath: process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  args: ['--no-sandbox', '--hide-scrollbars', '--force-color-profile=srgb', '--ignore-certificate-errors', '--font-render-hinting=none'],
  acceptInsecureCerts: true,
})
try {
  const page = await browser.newPage()
  await page.setViewport({ width: 393, height: 852, deviceScaleFactor: 3, isMobile: true, hasTouch: true })
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle2' })
  await page.evaluate(async () => {
    await fetch('/api/auth/logout', { method: 'POST' }).catch(() => undefined)
    const me = await (await fetch('/api/auth/demo', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ role: 'farmer' }) })).json()
    localStorage.setItem('ar.lang.v2', JSON.stringify('en'))
    localStorage.setItem(`ar.tour.v1:${me.id ?? 'guest'}`, '1')
    // The demo district's rice field, so Scan opens on a field.
    const farms = await (await fetch('/api/farms?lang=en')).json()
    const rice = farms.find((f) => f.crop === 'rice' && !f.read_only) ?? farms.find((f) => f.crop === 'rice') ?? farms[0]
    if (rice) localStorage.setItem('ar.farm', JSON.stringify(rice.id))
  })
  const dismiss = () => page.evaluate(() => [...document.querySelectorAll('button')].find((x) => /^Not now$/.test((x.textContent || '').trim()))?.click())
  // A real iPhone reports these insets; headless Chrome reports zero, so the
  // app's own env(safe-area-inset-*) padding is given the iPhone's numbers.
  // Once the page scrolls, the bar gets the frosted backing iOS gives it.
  const iphone = async () => {
    await page.addStyleTag({ content: `
      header { padding-top: 54px !important; }
      nav.fixed.bottom-0 { padding-bottom: 30px !important; }
      #ios-bar { position: fixed; inset: 0 0 auto 0; height: 54px; z-index: 2147483647; pointer-events: none;
        display: flex; align-items: center; justify-content: space-between; padding: 4px 30px 0 52px;
        font: 600 17px/1 -apple-system, "SF Pro Text", system-ui; color: #111; letter-spacing: -0.2px; }
      #ios-bar.scrolled { background: rgba(250,248,242,0.94); backdrop-filter: blur(12px); }
      #ios-bar .island { position: absolute; left: 50%; top: 11px; width: 125px; height: 37px; margin-left: -62.5px; border-radius: 20px; background: #000; }
      #ios-home { position: fixed; left: 50%; bottom: 8px; width: 139px; height: 5px; margin-left: -69.5px; border-radius: 3px; background: #111; z-index: 2147483647; }
    ` })
    await page.evaluate(() => {
      const bar = document.createElement('div'); bar.id = 'ios-bar'
      bar.innerHTML = `<span>9:41</span><span class="island"></span>
        <svg width="78" height="13" viewBox="0 0 78 13" fill="#111" aria-hidden="true">
          <rect x="0" y="9" width="3.2" height="4" rx="1"/><rect x="4.8" y="6.5" width="3.2" height="6.5" rx="1"/>
          <rect x="9.6" y="3.8" width="3.2" height="9.2" rx="1"/><rect x="14.4" y="1" width="3.2" height="12" rx="1"/>
          <path d="M30.5 3.4a10 10 0 0 1 13 0l-1.3 1.4a8 8 0 0 0-10.4 0zM32.8 5.9a6.6 6.6 0 0 1 8.4 0l-1.3 1.4a4.7 4.7 0 0 0-5.8 0zM35 8.4a3.2 3.2 0 0 1 4 0L37 10.6z" transform="translate(-1 0.5)"/>
          <rect x="50.5" y="0.5" width="24" height="12" rx="3.6" fill="none" stroke="#111" stroke-opacity=".4"/>
          <rect x="52.5" y="2.5" width="20" height="8" rx="2"/><rect x="75.7" y="4.3" width="1.6" height="4.4" rx=".8" fill-opacity=".45"/>
        </svg>`
      document.body.appendChild(bar)
      const home = document.createElement('div'); home.id = 'ios-home'; document.body.appendChild(home)
    })
  }
  const snap = async (name, scrollTo) => {
    await page.evaluate((re) => {
      const bar = document.getElementById('ios-bar')
      if (!re) { window.scrollTo(0, 0); bar.classList.remove('scrolled'); return }
      const rx = new RegExp(re, 'i')
      const h = [...document.querySelectorAll('main h2, main h3, main p, main span')].find((e) => rx.test(e.textContent || '') && e.children.length < 4)
      const top = (h?.closest('section') ?? h)?.getBoundingClientRect().top ?? 0
      window.scrollBy(0, top - 70); bar.classList.add('scrolled')
    }, scrollTo ?? null)
    await sleep(900)
    await page.screenshot({ path: join(OUT, `${name}.png`) })
    console.log('->', join(OUT, `${name}.png`))
  }

  // Scan.
  await page.goto(`${BASE}/app/scan`, { waitUntil: 'networkidle2' })
  await sleep(3500); await dismiss()
  await iphone(); await snap('scan')

  // A sample photo through the model: the answer, then what to do.
  await page.evaluate(() => {
    const s = [...document.querySelectorAll('main button')].filter((b) => b.querySelector('img'))
    ;(s.find((b) => /false smut/i.test(b.textContent || '')) ?? s[0]).click()
  })
  await sleep(2400)
  await page.evaluate(() => [...document.querySelectorAll('main button')].find((b) => /Check this photo/.test(b.textContent || ''))?.click())
  await page.waitForFunction(() => /\/app\/result/.test(location.pathname), { timeout: 60000 })
  await sleep(4500); await dismiss()
  await iphone(); await snap('result')
  await snap('treat', 'Do NOT do this')

  // The same answer in Marathi.
  await page.evaluate(() => window.scrollTo(0, 0)); await sleep(500)
  await page.click('header button[aria-haspopup="dialog"]')
  await sleep(1200)
  await page.evaluate(() => [...document.querySelectorAll('[role=dialog] button')].find((x) => /मराठी/.test(x.textContent || ''))?.click())
  await sleep(4500)
  await snap('result-mr')
  await page.evaluate(() => localStorage.setItem('ar.lang.v2', JSON.stringify('en')))
} finally { await browser.close() }
