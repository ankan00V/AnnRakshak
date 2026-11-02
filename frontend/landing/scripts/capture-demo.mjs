// Film the real app, screen by screen, for the hero demo.
//
// The hero used to be a drawing of the product. These are the product: the
// actual farmer app at phone width, driven the way a farmer drives it, with
// every screen saved as it really renders. If the app changes, re-run this
// and the hero stops being a lie.
//
//   node capture.mjs            # expects the dev server on :5174

import { mkdirSync, rmSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import puppeteer from 'puppeteer'

const BASE = process.env.BASE ?? 'http://localhost:5174'
const OUT = '/Users/ankanghosh/Developer/SIH/frontend/landing/public/demo'
// The app's own area on an iPhone 18 Pro, in points: the 402 x 874 screen
// less the 62pt status bar and the 34pt home indicator. Captured at exactly
// this size, the frames drop into the kit's phone where iOS would put them —
// the clock, signal and battery belong to the phone, the rest to the app,
// and neither is ever drawn over the other.
const W = 402, H = 778

mkdirSync(OUT, { recursive: true })

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const clickText = async (page, re, { tag = 'button, a, [role=button]' } = {}) => {
  const handle = await page.evaluateHandle((sel, src) => {
    const rx = new RegExp(src)
    return [...document.querySelectorAll(sel)].find((el) => rx.test(el.textContent || '')) ?? null
  }, tag, re.source)
  const el = handle.asElement()
  if (!el) return false
  await el.click()
  return true
}

// The tour offer covers the screen on a field's first visit and swallows
// every click after it. Seeding its "seen" key did not take for a new field,
// so it is dismissed the way a farmer dismisses it.
const dismissTour = async (page) => {
  for (let i = 0; i < 3; i++) {
    const gone = await page.evaluate(() => {
      const b = [...document.querySelectorAll('button')]
        .find((x) => /^(Not now|आत्ता नाही)$/.test((x.textContent || '').trim()))
      if (b) { b.click(); return false }
      return true
    })
    if (gone) return
    await sleep(800)
  }
}

const shot = async (page, name, { full = false } = {}) => {
  await sleep(600)
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: full })
  console.log('  saved', name, full ? '(full page)' : '')
}

// Puppeteer's own Chrome download is 150 MB nobody needs; the machine
// already has one. Override with CHROME=/path/to/binary.
const CHROME = process.env.CHROME
  ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

const browser = await puppeteer.launch({
  headless: 'new',
  executablePath: CHROME,
  args: ['--no-sandbox', '--hide-scrollbars', '--force-color-profile=srgb'],
})
const page = await browser.newPage()
await page.setViewport({ width: W, height: H, deviceScaleFactor: 2 })

try {
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle2' })

  // Sign in as the demo farmer, then put the app where a farmer leaves it:
  // a field chosen and the tour already seen. Clicking through the picker
  // was flaky — the header's own language button answers to "English" too,
  // so the sheet opened and swallowed the next click.
  const farmId = await page.evaluate(async (want) => {
    const r = await fetch('/api/auth/demo', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role: 'farmer' }),
    })
    const me = await r.json()
    const farms = await (await fetch('/api/farms?lang=en')).json()
    const wanted = Number(want) || null
    const rice = (Array.isArray(farms) ? farms : []).find((f) => f.id === wanted)
      ?? (Array.isArray(farms) ? farms : []).find((f) => f.crop === 'rice')
      ?? { id: me.farm_ids?.[0] }
    localStorage.setItem('ar.farm', JSON.stringify(rice.id))
    localStorage.setItem('ar.lang.v2', JSON.stringify('en'))
    localStorage.setItem(`ar.tour.v1:${rice.id}`, '1')
    return rice.id
  }, process.env.FARM ?? '')
  console.log('  field:', farmId)

  await page.goto(`${BASE}/app`, { waitUntil: 'networkidle2' })
  await sleep(4000)
  await dismissTour(page)
  await page.evaluate(() => window.scrollTo(0, 0))
  await shot(page, 'home-en')

  // The language sheet, open over the screen it is about to change.
  await clickText(page, /^English$/, { tag: 'header button, button' })
  await sleep(1100)
  await shot(page, 'lang-open')
  await page.keyboard.press('Escape')
  await sleep(700)

  await page.goto(`${BASE}/app/scan`, { waitUntil: 'networkidle2' })
  await sleep(3500)
  await dismissTour(page)
  await page.evaluate(() => window.scrollTo(0, 0))
  await shot(page, 'scan-en')

  // One of the tagged ICAR samples the scan screen ships, run through the
  // real pipeline: the gate, not a canned string, decides what comes back.
  const opened = await page.evaluate(() => {
    const samples = [...document.querySelectorAll('button')].filter((b) => b.querySelector('img'))
    // Tagged samples are the ones the gate questions or escalates; the
    // untagged one is the path a farmer sees most, so that is the hero's.
    const plain = samples.find((b) => !/asks|expert|retake|प्रश्न|तज्ज्ञ/i.test(b.textContent || ''))
    const el = plain ?? samples[0]
    el?.click()
    return !!el
  })
  console.log('  sample opened:', opened)
  await sleep(1800)
  await page.evaluate(() => window.scrollTo(0, 0))
  await shot(page, 'framed-en')          // the leaf in the frame, before it is read

  // Choosing a sample only loads it. The farmer still presses Scan, and that
  // is the press the whole product hangs on, so it gets its own frame.
  await clickText(page, /^(Scan|तपासणी)$/)
  await sleep(9000)
  await dismissTour(page)
  // The photograph is the top of the result; the verdict is under it, and the
  // verdict is the point.
  // Three real screens rather than one tall one. A full-page shot bakes the
  // fixed bottom bar into the middle of the image, which looks like a bug in
  // the app; scrolling and shooting gives frames that each look like the app.
  for (const [i, y] of [0, 540, 1120].entries()) {
    await page.evaluate((to) => window.scrollTo(0, to), y)
    await sleep(900)
    await shot(page, `result-en-${i}`)
  }
  await page.evaluate(() => window.scrollTo(0, 0))

  // The same verdict in her own language: the payoff beat.
  await dismissTour(page)
  await clickText(page, /^English$/, { tag: 'header button, button' })
  await sleep(1200)
  await clickText(page, /मराठी/)
  await sleep(3500)
  await page.evaluate(() => window.scrollTo(0, 400))
  await sleep(900)
  await shot(page, 'result-mr')

  // 2x PNGs are 3.8 MB; the same frames as 1x webp are 280 KB, which is the
  // whole point — this set replaced an 11.4 MB video.
  console.log('  converting to webp…')
  execFileSync(process.env.PY ?? '/Users/ankanghosh/Developer/SIH/.venv/bin/python', ['-c', `
from PIL import Image
import pathlib
for f in sorted(pathlib.Path(${JSON.stringify(OUT)}).glob('*.png')):
    im = Image.open(f).convert('RGB')
    im.thumbnail((im.width // 2, im.height // 2))
    im.save(f.with_suffix('.webp'), 'WEBP', quality=86, method=6)
    f.unlink()
`], { stdio: 'inherit' })

  console.log('done ->', OUT)
} finally {
  await browser.close()
}
