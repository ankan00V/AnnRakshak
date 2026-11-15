// Renders index.html frame by frame (every frame is render(t)) and encodes
// the frames with the soundtrack.
//
//   node render.mjs stills 3.9 26.4 ...   -> out/stills/t_<sec>.jpg
//   ./run.sh                              -> out/annrakshak-launch.mp4
//
// Frames go to disk first, so a crash costs one frame, not the render; a
// re-run picks up after the last frame written. A long-running page wears
// out (around 3,200 frames it stopped drawing images, then hung), so each run
// renders at most MAX frames with a fresh browser and exits with code 3;
// run.sh loops until every frame exists, then ffmpeg runs once.
import http from 'node:http'
import { existsSync, mkdirSync, readFileSync, realpathSync, statSync, writeFileSync } from 'node:fs'
import { extname, join, resolve, sep } from 'node:path'
import { spawn } from 'node:child_process'
import puppeteer from 'puppeteer-core'

const HERE = new URL('.', import.meta.url).pathname
const OUT = join(HERE, 'out')
const PUB = join(HERE, '../../public')
const TL = JSON.parse(readFileSync(join(OUT, 'timeline.json'), 'utf8'))
const META = JSON.parse(readFileSync(join(OUT, 'shotsv/meta.json'), 'utf8'))
const FPS = 30, DUR = TL.dur
const POSTER = Number(process.env.POSTER ?? 3.9)   // the hook, settled: the answer with its heat map
const MAX = Number(process.env.MAX ?? 600)
const TYPES = { '.html': 'text/html', '.png': 'image/png', '.webp': 'image/webp', '.woff2': 'font/woff2', '.jpg': 'image/jpeg', '.json': 'application/json' }

// Serves only these three folders, and only to this machine: a path that
// resolves outside them ("/pub/../../.env") is refused, and nothing on the
// network can reach the server while a render runs.
const ROOTS = { pub: realpathSync(PUB), shots: realpathSync(join(OUT, 'shotsv')), here: realpathSync(HERE) }
const server = http.createServer((req, res) => {
  let u
  try { u = decodeURIComponent(new URL(req.url, 'http://x').pathname) } catch { res.writeHead(400); return res.end() }
  const [root, rel] = u.startsWith('/pub/') ? [ROOTS.pub, u.slice(5)]
    : u.startsWith('/shots/') ? [ROOTS.shots, u.slice(7)]
    : [ROOTS.here, u === '/' ? 'index.html' : u.slice(1)]
  const want = resolve(root, rel)
  if (!want.startsWith(root + sep) || !existsSync(want)) { res.writeHead(404); return res.end() }
  const file = realpathSync(want)  // a symlink may not lead out either
  if (!file.startsWith(root + sep) || !statSync(file).isFile()) { res.writeHead(404); return res.end() }
  res.writeHead(200, { 'Content-Type': TYPES[extname(file)] ?? 'application/octet-stream' })
  res.end(readFileSync(file))
}).listen(0, '127.0.0.1')

const browser = await puppeteer.launch({
  headless: 'new', executablePath: process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  args: ['--no-sandbox', '--force-color-profile=srgb', '--hide-scrollbars', '--font-render-hinting=none', '--disable-lcd-text'],
  protocolTimeout: 60000,
})
const page = await browser.newPage()
await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 })
await page.evaluateOnNewDocument((tl, meta) => { window.TL = tl; window.META = meta }, TL, META)
await page.goto(`http://127.0.0.1:${server.address().port}/`, { waitUntil: 'networkidle0' })
await page.evaluate(() => window.ready)

const frame = async (t) => {
  await page.evaluate((t) => window.render(t), t)
  return page.screenshot({ type: 'jpeg', quality: 94, optimizeForSpeed: true })
}

try {
  if (process.argv[2] === 'stills') {
    mkdirSync(join(OUT, 'stills'), { recursive: true })
    for (const s of process.argv.slice(3)) {
      const t = Number(s)
      writeFileSync(join(OUT, 'stills', `t_${t.toFixed(2)}.jpg`), await frame(t))
    }
    console.log('stills ->', join(OUT, 'stills'))
  } else {
    const dir = join(OUT, 'frames')
    mkdirSync(dir, { recursive: true })
    const n = Math.round(DUR * FPS)
    let made = 0
    for (let i = 0; i < n; i++) {
      const f = join(dir, `f_${String(i).padStart(5, '0')}.jpg`)
      if (existsSync(f)) continue
      if (made++ >= MAX) { console.log('  pausing for a fresh browser at', i); process.exitCode = 3; break }
      // Frame 0 is the poster, so every platform's thumbnail shows a settled
      // frame. It replaces frame 0; duration and sync are unchanged.
      writeFileSync(f, await frame(i === 0 ? POSTER : i / FPS))
    }
    if (process.exitCode !== 3) {
      const ff = spawn('ffmpeg', ['-y', '-v', 'error', '-framerate', String(FPS), '-i', join(dir, 'f_%05d.jpg'),
        '-i', join(OUT, 'music.wav'),
        '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', '-profile:v', 'high', '-tune', 'film',
        '-c:a', 'aac', '-b:a', '192k', '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11',
        '-t', String(DUR), '-movflags', '+faststart', join(OUT, 'annrakshak-launch.mp4')], { stdio: 'inherit' })
      const code = await new Promise((r) => ff.on('close', r))
      console.log('done, ffmpeg', code)
    }
  }
} finally {
  await browser.close()
  server.close()
}
