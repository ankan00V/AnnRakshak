// Film the real app, screen by screen, for the landing page's phones.
//
// The hero used to be a drawing of the product. These are the product: the
// actual farmer app at phone width, driven the way a farmer drives it, with
// every screen saved as it really renders. If the app changes, re-run this
// and the landing page stops being a lie.
//
//   npm i --no-save puppeteer-core     # once; it drives the Chrome already here
//   BASE=https://localhost:5176 node scripts/capture-demo.mjs
//
// The account is the demo farmer. Its own fields can be scanned (the shared,
// seeded showcase fields are read-only), so run it against a database where
// the demo farmer has registered a rice field — an isolated one, never the
// real one. It prints where each tapped control sits on its frame and the
// colours at the top and bottom of the screen: ScanDemo.tsx's TAPS and its
// phone wallpaper are copied from that output.

import { mkdirSync } from 'node:fs'
import { execFileSync } from 'node:child_process'

// puppeteer-core is enough (it brings no browser of its own); a full
// puppeteer install works too.
const puppeteer = await import('puppeteer-core').then((m) => m.default)
  .catch(() => import('puppeteer').then((m) => m.default))

const BASE = process.env.BASE ?? 'http://localhost:5174'
const OUT = process.env.OUT ?? new URL('../public/demo', import.meta.url).pathname
// The app's own area on an iPhone 18 Pro, in points: the 402 x 874 screen
// less the 62pt status bar and the 34pt home indicator. Captured at exactly
// this size, the frames drop into the kit's phone where iOS would put them —
// the clock, signal and battery belong to the phone, the rest to the app,
// and neither is ever drawn over the other.
const W = 402, H = 778

mkdirSync(OUT, { recursive: true })

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// The tour offer covers the screen on a field's first visit and swallows
// every click after it; dismissed the way a farmer dismisses it.
const dismissTour = async (page) => {
  for (let i = 0; i < 3; i++) {
    const gone = await page.evaluate(() => {
      const b = [...document.querySelectorAll('button')]
        .find((x) => /^(Not now|आत्ता नाही|अभी नहीं)$/.test((x.textContent || '').trim()))
      if (b) { b.click(); return false }
      return true
    })
    if (gone) return
    await sleep(800)
  }
}

const shot = async (page, name) => {
  await sleep(700)
  await page.screenshot({ path: `${OUT}/${name}.png` })
  console.log('  saved', name)
}

/** Where a control sits on the frame, as a share of the screen: the hero's
 *  cursor taps a photograph, so it is placed against what the photograph
 *  shows. */
const taps = {}
const where = async (page, key, selector, match) => {
  const at = await page.evaluate((sel, src, w, h) => {
    const rx = src ? new RegExp(src) : null
    const el = [...document.querySelectorAll(sel)]
      .find((e) => e.getBoundingClientRect().width > 0 && (!rx || rx.test(e.textContent || e.getAttribute('aria-label') || '')))
    if (!el) return null
    const r = el.getBoundingClientRect()
    return { x: +((r.left + r.width / 2) / w).toFixed(3), y: +((r.top + r.height / 2) / h).toFixed(3) }
  }, selector, match?.source ?? null, W, H)
  taps[key] = at
  return at
}

/** Scroll so `heading` sits just under the top of the screen. */
const scrollToHeading = async (page, re, gap = 24) => {
  const ok = await page.evaluate((src, g) => {
    const rx = new RegExp(src)
    const h = [...document.querySelectorAll('main h2, main h3')].find((e) => rx.test(e.textContent || ''))
    if (!h) return false
    const top = h.closest('section')?.getBoundingClientRect().top ?? h.getBoundingClientRect().top
    window.scrollBy(0, top - g)
    return true
  }, re.source, gap)
  await sleep(900)
  return ok
}

const CHROME = process.env.CHROME
  ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

const browser = await puppeteer.launch({
  headless: 'new',
  executablePath: CHROME,
  // The isolated dev server is HTTPS with a self-signed certificate.
  args: ['--no-sandbox', '--hide-scrollbars', '--force-color-profile=srgb', '--ignore-certificate-errors'],
  acceptInsecureCerts: true,
})
const page = await browser.newPage()
await page.setViewport({ width: W, height: H, deviceScaleFactor: 2, isMobile: true, hasTouch: true })

try {
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle2' })

  // Sign in as the demo farmer, then put the app where a farmer leaves it:
  // their own rice field chosen and the tour already seen.
  const farmId = await page.evaluate(async (want) => {
    const r = await fetch('/api/auth/demo', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role: 'farmer' }),
    })
    const me = await r.json()
    const farms = await (await fetch('/api/farms?lang=en')).json()
    const list = Array.isArray(farms) ? farms : []
    let own = list.filter((f) => !f.read_only)
    // Each demo sign-in is a fresh account. With no field of its own, it
    // registers one the way the app's form does: a rice field in Bhandara,
    // transplanted 81 days ago.
    if (!own.some((f) => f.crop === 'rice')) {
      const sown = new Date(Date.now() - 81 * 864e5).toISOString().slice(0, 10)
      const made = await (await fetch('/api/farms', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          farmer_name: me.name || 'Demo farmer', lang: 'en', crop: 'rice', sowing_date: sown,
          date_basis: 'transplanted', state: 'Maharashtra', district: 'Bhandara', village: 'Bhandara',
          lat: 21.1667, lon: 79.65, area_acres: 2, irrigation: 'canal',
        }),
      })).json()
      own = [made, ...own]
    }
    const rice = list.find((f) => f.id === (Number(want) || null))
      ?? own.find((f) => f.crop === 'rice') ?? own[0] ?? list[0]
    localStorage.setItem('ar.farm', JSON.stringify(rice.id))
    localStorage.setItem('ar.lang.v2', JSON.stringify('en'))
    localStorage.setItem(`ar.tour.v1:${me.id ?? me.user?.id ?? 'guest'}`, '1')
    return { id: rice.id, readOnly: !!rice.read_only }
  }, process.env.FARM ?? '')
  console.log('  field:', farmId)
  if (farmId.readOnly) console.log('  !! that field is a shared demo field: its samples cannot be scanned')

  await page.goto(`${BASE}/app`, { waitUntil: 'networkidle2' })
  await sleep(4000)
  await dismissTour(page)
  await page.evaluate(() => window.scrollTo(0, 0))
  await where(page, 'home', 'nav a[href="/app/scan"]')
  await shot(page, 'home-en')

  const langButton = 'header button[aria-haspopup="dialog"]'

  await page.goto(`${BASE}/app/scan`, { waitUntil: 'networkidle2' })
  await sleep(3500)
  await dismissTour(page)
  await page.evaluate(() => window.scrollTo(0, 0))
  await shot(page, 'scan-en')                   // the camera: "photograph a sick plant"
  // The samples are under the camera: bring them up, as a farmer scrolls to them.
  await scrollToHeading(page, /ICAR test photos|sample/i, 90)
  // An untagged sample: the path a farmer sees most, so it is the hero's.
  const plain = await page.evaluate(() => {
    const samples = [...document.querySelectorAll('main button')].filter((b) => b.querySelector('img'))
    const el = samples.find((b) => !/asks|expert|retake|question/i.test(b.textContent || '')) ?? samples[0]
    if (!el) return null
    el.setAttribute('data-capture', 'sample')
    return true
  })
  await where(page, 'samples', '[data-capture=sample]')
  await shot(page, 'samples-en')
  if (!plain) throw new Error('no sample photographs on the scan screen')
  await page.click('[data-capture=sample]')
  await sleep(2200)
  await page.evaluate(() => window.scrollTo(0, 0))
  // The press the whole product hangs on gets its own frame.
  await where(page, 'framed', 'main button', /^\s*(Check this photo|Check|Scan)\s*$/)
  await shot(page, 'framed-en')

  const pressed = await page.evaluate(() => {
    const b = [...document.querySelectorAll('main button')].find((x) => /Check this photo|^Check$|^Scan$/.test((x.textContent || '').trim()))
    b?.click()
    return !!b
  })
  if (!pressed) throw new Error('no Check button after choosing the sample')
  await page.waitForFunction(() => /\/app\/result/.test(location.pathname), { timeout: 60000 })
  await sleep(4500)
  await dismissTour(page)

  // Three real screens rather than one tall one: a full-page shot bakes the
  // fixed bottom bar into the middle of the image, which looks like a bug.
  await page.evaluate(() => window.scrollTo(0, 0))
  await shot(page, 'result-en-0')               // the photo, the name, how sure
  await scrollToHeading(page, /Do NOT do this|not to do|avoid/i)
  await shot(page, 'result-en-1')               // what not to do, then the safest step
  if (!(await scrollToHeading(page, /Proven by ICAR|expert|call/i))) await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
  await shot(page, 'result-en-2')               // who to ask, and the ICAR referral

  // The same answer in her own language: the payoff beat. On a phone the
  // header scrolls away, so the language button is pressed from the top of
  // the answer, and the sheet opens over the screen it is about to change.
  await page.evaluate(() => window.scrollTo(0, 0))
  await sleep(700)
  await where(page, 'verdict', langButton)
  await page.click(langButton)
  await sleep(1100)
  await where(page, 'lang', '[role=dialog] button[lang]', /मराठी/)
  await shot(page, 'lang-open')
  await page.evaluate(() => [...document.querySelectorAll('[role=dialog] button')].find((b) => /मराठी/.test(b.textContent || ''))?.click())
  await sleep(4500)
  // Past the photograph to the name, how sure, and what not to do.
  await page.evaluate(() => window.scrollTo(0, 380))
  await sleep(900)
  await shot(page, 'result-mr')

  // The colours at the very top and bottom of the home frame: the phone's
  // wallpaper runs them up behind the clock and down behind the home bar.
  // 2x PNGs are megabytes; the same frames as 1x webp are a few hundred KB.
  console.log('  converting to webp…')
  execFileSync(process.env.PY ?? new URL('../../../.venv/bin/python', import.meta.url).pathname, ['-c', `
from PIL import Image
import pathlib
out = pathlib.Path(${JSON.stringify(OUT)})
home = Image.open(out / 'home-en.png').convert('RGB')
print('  wallpaper top', '#%02x%02x%02x' % home.getpixel((home.width // 2, 2)),
      'bottom', '#%02x%02x%02x' % home.getpixel((home.width // 2, home.height - 3)))
for f in sorted(out.glob('*.png')):
    im = Image.open(f).convert('RGB')
    im.thumbnail((im.width // 2, im.height // 2), Image.LANCZOS)
    im.save(f.with_suffix('.webp'), 'WEBP', quality=86, method=6)
    f.unlink()
`], { stdio: 'inherit' })

  console.log('  TAPS', JSON.stringify(taps))
  console.log('done ->', OUT)
} finally {
  await browser.close()
}
