// Every screen the launch video shows, captured from the running app.
//
// Phone screens at 402 x 874 (3x), laptop screens at 1512 x 945 (2x), into
// out/shots, with the tap positions and scroll offsets the video needs in
// out/shots/meta.json. Nothing is drawn or mocked: these are the app.
//
//   ISO   https://localhost:5176  the app against the isolated database
//                                 (launch config "landing-isolated" +
//                                 "backend-isolated", SMS_BACKEND=outbox):
//                                 the demo farmer owns a rice field it can
//                                 scan, so every flow that writes runs here.
//   MAIN  https://localhost:5177  the app against the development database
//                                 ("landing-main" + "backend"): the full demo
//                                 district, read only.
//   BUILT http://localhost:8014   the production build ("web-built"), whose
//                                 service worker keeps the app offline.
//
//   STEP=iso|call|main|officer|offline node capture.mjs   (default: all)
import { execFileSync } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import puppeteer from 'puppeteer-core'

const HERE = new URL('.', import.meta.url).pathname
const REPO = join(HERE, '../../../..')
const OUT = join(HERE, 'out/shots')
const CLIP = join(HERE, 'out/clip/field_check.mp4')
const CAM = join(HERE, 'out/clip/fake_cam.y4m')
const ISO = 'https://localhost:5176', MAIN = 'https://localhost:5177', BUILT = 'http://localhost:8014'
const STEP = process.env.STEP ?? 'all'
const want = (s) => STEP === 'all' || STEP.split(',').includes(s)
mkdirSync(OUT, { recursive: true })
const META_FILE = join(OUT, 'meta.json')
const meta = existsSync(META_FILE) ? JSON.parse(readFileSync(META_FILE, 'utf8')) : {}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const browser = await puppeteer.launch({
  headless: 'new',
  executablePath: process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  args: ['--no-sandbox', '--hide-scrollbars', '--force-color-profile=srgb', '--ignore-certificate-errors', '--font-render-hinting=none',
    // The live call's camera: a clip of ICAR photographs, as a phone would see them.
    '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-video-capture=${CAM}`,
    '--autoplay-policy=no-user-gesture-required'],
  acceptInsecureCerts: true,
})
const PHONE = { width: 402, height: 874, deviceScaleFactor: 3, isMobile: true, hasTouch: true }
const LAPTOP = { width: 1512, height: 945, deviceScaleFactor: 2 }

/** Sign in as the demo farmer or expert. A fresh isolated database gives the
 *  demo farmer no field of its own, so it registers one the way the app's
 *  form does: rice in Bhandara, transplanted 81 days ago. */
async function signIn(page, base, role) {
  await page.goto(`${base}/`, { waitUntil: 'networkidle2' })
  return page.evaluate(async (role) => {
    await fetch('/api/auth/logout', { method: 'POST' }).catch(() => undefined)
    const me = await (await fetch('/api/auth/demo', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ role }) })).json()
    localStorage.setItem('ar.lang.v2', JSON.stringify('en'))
    localStorage.setItem(`ar.tour.v1:${me.id ?? 'guest'}`, '1')
    if (role !== 'farmer') return { id: me.id }
    let farms = await (await fetch('/api/farms?lang=en')).json()
    let own = farms.filter((f) => !f.read_only)
    if (!farms.some((f) => f.crop === 'rice')) {
      const sown = new Date(Date.now() - 81 * 864e5).toISOString().slice(0, 10)
      await fetch('/api/farms', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
        farmer_name: me.name || 'Demo farmer', lang: 'en', crop: 'rice', sowing_date: sown, date_basis: 'transplanted',
        state: 'Maharashtra', district: 'Bhandara', village: 'Bhandara', lat: 21.1667, lon: 79.65, area_acres: 2, irrigation: 'canal',
      }) })
      farms = await (await fetch('/api/farms?lang=en')).json()
      own = farms.filter((f) => !f.read_only)
    }
    const rice = own.find((f) => f.crop === 'rice') ?? farms.find((f) => f.crop === 'rice') ?? farms[0]
    localStorage.setItem('ar.farm', JSON.stringify(rice.id))
    return { id: me.id, farm: rice.id, readOnly: !!rice.read_only, phone: me.phone, sms: me.sms_available }
  }, role)
}
const dismiss = (page) => page.evaluate(() => [...document.querySelectorAll('button')].find((x) => /^Not now$/.test((x.textContent || '').trim()))?.click())
async function go(page, url, wait = 3500) {
  await page.goto(url, { waitUntil: 'networkidle2' }); await sleep(wait); await dismiss(page)
  await page.evaluate(() => window.scrollTo(0, 0)); await sleep(400)
}
async function shot(page, name, opts = {}) { await sleep(500); await page.screenshot({ path: join(OUT, `${name}.png`), ...opts }); console.log('  ', name) }
const click = (page, re, scope = 'button') => page.evaluate((src, sel) => {
  const b = [...document.querySelectorAll(sel)].find((x) => new RegExp(src).test((x.textContent || '') + ' ' + (x.getAttribute('aria-label') || '')))
  b?.click(); return !!b
}, re.source, scope)
/** Centre of the first matching element, as a share of the viewport. */
async function pos(page, key, selector, re) {
  const vp = page.viewport()
  meta[key] = await page.evaluate((sel, src, w, h) => {
    const rx = src ? new RegExp(src) : null
    const el = [...document.querySelectorAll(sel)].find((e) => e.getBoundingClientRect().width > 0
      && (!rx || rx.test((e.textContent || '') + ' ' + (e.getAttribute('aria-label') || ''))))
    if (!el) return null
    const r = el.getBoundingClientRect()
    return { x: +((r.left + r.width / 2) / w).toFixed(4), y: +((r.top + r.height / 2) / h).toFixed(4) }
  }, selector, re ? re.source : null, vp.width, vp.height)
}
/** Page-top of the section holding text that matches, in CSS px. */
const yOf = (page, re) => page.evaluate((src) => {
  const rx = new RegExp(src, 'i')
  const h = [...document.querySelectorAll('main h1, main h2, main h3, main p, main span')].find((e) => rx.test(e.textContent || '') && e.children.length < 4)
  if (!h) return null
  return Math.round((h.closest('section') ?? h).getBoundingClientRect().top + window.scrollY)
}, re.source)
/** The page as one tall picture, the fixed bar and Krishi left out: the video
 *  scrolls it under the bar, captured on its own by chrome(). */
async function tall(page, name) {
  meta[`${name}_h`] = await page.evaluate(() => document.documentElement.scrollHeight)
  const css = await page.addStyleTag({ content: 'nav.fixed, [data-tour="krishi"]{visibility:hidden!important}' })
  await shot(page, name, { fullPage: true })
  await css.evaluate((n) => n.remove())
}
/** The bottom bar and Krishi alone, transparent everywhere else. */
async function chrome(page, name) {
  const css = await page.addStyleTag({ content: `
    html, body { background: transparent !important; }
    body * { visibility: hidden !important; }
    nav.fixed, nav.fixed *, [data-tour="krishi"], [data-tour="krishi"] * { visibility: visible !important; }
    #root > * > *:not(nav) { background: transparent !important; }` })
  await page.evaluate(() => window.scrollTo(0, 0))
  await shot(page, name, { omitBackground: true })
  await css.evaluate((n) => n.remove())
}
async function runSample(page, base, pick) {
  await go(page, `${base}/app/scan`)
  await page.evaluate((src) => {
    const s = [...document.querySelectorAll('main button')].filter((b) => b.querySelector('img'))
    s.find((b) => new RegExp(src, 'i').test(b.textContent || ''))?.click()
  }, pick)
  await sleep(2400)
  await click(page, /Check this photo/)
  await page.waitForFunction(() => /\/app\/result/.test(location.pathname), { timeout: 60000 })
  await sleep(4500); await dismiss(page); await page.evaluate(() => window.scrollTo(0, 0)); await sleep(500)
}

try {
  if (want('iso')) {
    const page = await browser.newPage(); await page.setViewport(PHONE)
    const who = await signIn(page, ISO, 'farmer')
    console.log('ISO farmer', who)
    // The SMS panel needs a phone number on the account: a fictional one, in
    // the isolated database only.
    if (!who.phone) {
      execFileSync(join(REPO, '.venv/bin/python'), ['-c', `
import sqlite3; c = sqlite3.connect(${JSON.stringify(join(HERE, 'out/isolated/app.db'))})
c.execute("update app_user set phone='9800012345' where id=? and is_demo=1", (${who.id},)); c.commit()`])
    }

    // The scan: camera screen, the ICAR samples, a sample framed, checking, the answer.
    await go(page, `${ISO}/app/scan`)
    await shot(page, 'p_scan')
    await chrome(page, 'p_chrome_scan')
    await page.evaluate(() => {
      const h = [...document.querySelectorAll('main h2, main h3')].find((e) => /ICAR test photos/.test(e.textContent || ''))
      window.scrollBy(0, h.closest('section').getBoundingClientRect().top - 90)
    })
    await sleep(900)
    await page.evaluate(() => {
      const s = [...document.querySelectorAll('main button')].filter((b) => b.querySelector('img'))
      ;(s.find((b) => /false smut/i.test(b.textContent || '')) ?? s[0]).setAttribute('data-cap', 'sample')
    })
    await pos(page, 'tap_sample', '[data-cap=sample]')
    await shot(page, 'p_samples')
    await page.click('[data-cap=sample]')
    await sleep(2400)
    await page.evaluate(() => window.scrollTo(0, 0))
    await pos(page, 'tap_check', 'main button', /Check this photo/)
    await shot(page, 'p_framed')
    await click(page, /Check this photo/)
    await sleep(450)
    await shot(page, 'p_checking1')
    await page.waitForFunction(() => /\/app\/result/.test(location.pathname), { timeout: 60000 })
    await sleep(4000); await dismiss(page); await page.evaluate(() => window.scrollTo(0, 0))
    await shot(page, 'p_result')
    meta.result_avoid = await yOf(page, /Do NOT do this/)
    meta.result_call = await yOf(page, /Call an expert if/)
    await tall(page, 'p_result_full')
    await pos(page, 'tap_lang', 'header button[aria-haspopup="dialog"]')
    await page.click('header button[aria-haspopup="dialog"]')
    await sleep(1200)
    await pos(page, 'tap_marathi', '[role=dialog] button[lang]', /मराठी/)
    await shot(page, 'p_lang')
    await click(page, /मराठी/, '[role=dialog] button')
    await sleep(4500); await page.evaluate(() => window.scrollTo(0, 0))
    await shot(page, 'p_result_mr')
    await page.evaluate(() => localStorage.setItem('ar.lang.v2', JSON.stringify('en')))

    // Unsure: a sample the gate asks a question about.
    await runSample(page, ISO, 'asks a question')
    await shot(page, 'p_clarify')

    // The live check's own screen, before the call.
    await go(page, `${ISO}/app/live`)
    await pos(page, 'tap_start', 'main button', /Start live check/)
    await shot(page, 'p_live')

    // Check before you spray: a weed killer, refused.
    await go(page, `${ISO}/app/spray`)
    await page.click('main form input')
    await page.type('main form input', 'Glyphosate', { delay: 60 })
    await sleep(400)
    await pos(page, 'tap_spray', 'main form button[type=submit]')
    await shot(page, 'p_spray_typed')
    await page.click('main form button[type=submit]')
    await sleep(6000)
    await page.evaluate(() => {
      const h = [...document.querySelectorAll('main h2, main h3, main p')].find((e) => /Do not spray this/.test(e.textContent || ''))
      h?.closest('section')?.scrollIntoView({ block: 'center' })
    })
    await sleep(900)
    await shot(page, 'p_spray_verdict')

    // Warnings by SMS.
    await signIn(page, ISO, 'farmer')
    await go(page, `${ISO}/app/profile`, 4000)
    const smsY = await yOf(page, /Warnings by SMS/)
    if (smsY != null) await page.evaluate((y) => window.scrollTo(0, Math.max(0, y - 120)), smsY)
    await sleep(800)
    await shot(page, 'p_profile_sms')
    await page.close()

    // Laptop: a photo uploaded on Scan, and the field check from a video.
    const lap = await browser.newPage(); await lap.setViewport(LAPTOP)
    await signIn(lap, ISO, 'farmer')
    await go(lap, `${ISO}/app/scan`)
    await shot(lap, 'l_scan')
    const img = await lap.$('input[type=file][accept^="image"]:not([capture])') ?? await lap.$('input[type=file][accept^="image"]')
    await img.uploadFile(process.env.PHOTO)
    await sleep(2500); await lap.evaluate(() => window.scrollTo(0, 0))
    await pos(lap, 'tap_lcheck', 'main button', /Check this photo/)
    await shot(lap, 'l_scan_framed')
    await click(lap, /Check this photo/)
    await lap.waitForFunction(() => /\/app\/result/.test(location.pathname), { timeout: 60000 })
    await sleep(4500); await dismiss(lap); await lap.evaluate(() => window.scrollTo(0, 0))
    await shot(lap, 'l_result')
    await go(lap, `${ISO}/app/live`)
    await pos(lap, 'tap_lvideo', 'main button', /Choose a video/)
    await shot(lap, 'l_live')
    await (await lap.$('input[type=file][accept^="video"]')).uploadFile(CLIP)
    await sleep(4500); await shot(lap, 'l_live_watch')
    await lap.waitForFunction(() => /What the video showed/.test(document.body.innerText), { timeout: 180000 }).catch(() => undefined)
    await sleep(2500); await lap.evaluate(() => window.scrollTo(0, 0))
    await shot(lap, 'l_live_result')
    await lap.close()
  }

  if (want('call')) {
    // The AI video call on a phone, the clip standing in for the camera.
    const page = await browser.newPage(); await page.setViewport(PHONE)
    await signIn(page, ISO, 'farmer')
    await go(page, `${ISO}/app/live`, 3000)
    console.log('   call started:', await click(page, /Start live check/))
    for (const [i, wait] of [[1, 5000], [2, 6000], [3, 7000], [4, 8000]]) {
      await sleep(wait); await shot(page, `p_call${i}`)
    }
    console.log('   call ended:', await click(page, /^\s*End\s*$|End call/))
    await sleep(12000); await page.evaluate(() => window.scrollTo(0, 0))
    await shot(page, 'p_call_result')
    await page.close()
  }

  if (want('main')) {
    const page = await browser.newPage(); await page.setViewport(PHONE)
    console.log('MAIN farmer', await signIn(page, MAIN, 'farmer'))
    await go(page, `${MAIN}/app`, 5000)
    await pos(page, 'tap_scan_nav', 'nav a[href="/app/scan"]')
    await shot(page, 'p_home')
    await chrome(page, 'p_chrome_home')
    meta.home_followup = await yOf(page, /How is your crop after the treatment/)
    meta.home_harvest = await yOf(page, /Expected harvest/)
    await tall(page, 'p_home_full')
    // Krishi: opened, then the first suggested question asked.
    await page.click('[data-tour="krishi"]')
    await sleep(1500)
    await pos(page, 'tap_krishi_q', '[role=dialog] button', /\?\s*$/)
    await shot(page, 'p_krishi_open')
    await page.evaluate(() => {
      const chips = [...document.querySelectorAll('[role=dialog] button')].filter((b) => /\?$/.test((b.textContent || '').trim()))
      ;(chips.find((b) => /today/i.test(b.textContent || '')) ?? chips[0])?.click()
    })
    await sleep(6000)
    await shot(page, 'p_krishi')
    await page.keyboard.press('Escape'); await sleep(600)
    await go(page, `${MAIN}/app/weather`, 5000)
    meta.weather_todo = await yOf(page, /What to do/)
    await chrome(page, 'p_chrome_weather')
    await tall(page, 'p_weather_full')
    await go(page, `${MAIN}/app/alerts`, 5000)
    await shot(page, 'p_alerts')
    await go(page, `${MAIN}/app/history`, 4500)
    await page.evaluate(() => {
      const links = [...document.querySelectorAll('main a[href^="/app/history/"]')]
      ;(links.find((a) => /expert|confirmed|corrected/i.test(a.textContent || '')) ?? links[0])?.click()
    })
    await sleep(4500); await page.evaluate(() => window.scrollTo(0, 0))
    await shot(page, 'p_problem')

    await page.setViewport(LAPTOP)
    await go(page, `${MAIN}/app`, 5000); await shot(page, 'l_farmer_home')
    await go(page, `${MAIN}/app/weather`, 5000); await shot(page, 'l_farmer_weather')
    await page.close()
  }

  if (want('officer')) {
    const page = await browser.newPage(); await page.setViewport(LAPTOP)
    console.log('MAIN expert', await signIn(page, MAIN, 'expert'))
    await go(page, `${MAIN}/officer`, 5000); await shot(page, 'l_today')
    await go(page, `${MAIN}/officer/queue?status=all`, 5000)
    await pos(page, 'tap_review', 'main button', /^\s*Review/)
    await shot(page, 'l_queue')
    await click(page, /^\s*Review/)
    await sleep(4000); await page.evaluate(() => window.scrollTo(0, 0))
    await shot(page, 'l_case')
    const dy = await yOf(page, /Your decision|Resolved/)
    if (dy != null) await page.evaluate((y) => window.scrollTo(0, Math.max(0, y - 140)), dy)
    await sleep(900); await shot(page, 'l_case_decision')
    await go(page, `${MAIN}/officer/map`, 7000); await shot(page, 'l_map')
    await go(page, `${MAIN}/officer/advisories`, 4000); await shot(page, 'l_advisories')
    await go(page, `${MAIN}/officer/inputs`, 4000); await shot(page, 'l_inputs')
    await go(page, `${MAIN}/officer/model`, 5000); await shot(page, 'l_model')
    await go(page, `${MAIN}/officer/officers`, 4000); await shot(page, 'l_officers')
    await go(page, `${MAIN}/officer`, 4500)
    await click(page, /Darpan/)
    await sleep(2500)
    await shot(page, 'l_darpan')
    await page.close()
  }

  if (want('offline')) {
    // Offline, from the production build: its service worker keeps the app.
    const page = await browser.newPage(); await page.setViewport(PHONE)
    await signIn(page, BUILT, 'farmer')
    for (const p of ['/app', '/app/weather', '/app']) { await page.goto(`${BUILT}${p}`, { waitUntil: 'networkidle2' }); await sleep(4500); await dismiss(page) }
    await sleep(4000)
    await page.setOfflineMode(true)
    await page.goto(`${BUILT}/app`, { waitUntil: 'domcontentloaded' }).catch(() => undefined)
    await sleep(5000); await dismiss(page)
    await page.evaluate(() => { history.pushState({}, '', '/app/weather'); dispatchEvent(new PopStateEvent('popstate')) })
    await sleep(3000)
    await shot(page, 'p_offline_weather')
    await page.close()
  }
} finally {
  writeFileSync(META_FILE, JSON.stringify(meta, null, 1))
  console.log(JSON.stringify(meta))
  await browser.close()
}
