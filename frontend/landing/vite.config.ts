import { createHash } from 'node:crypto'
import { existsSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { join, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

// A local certificate, when one has been made. Two reasons to bother in dev:
// Safari rewrites http://localhost to https and then cannot connect to a plain
// HTTP dev server, and getUserMedia only runs in a secure context — so the live
// field call cannot be tried on a real phone over the LAN without this.
//
//   cd frontend/landing/.certs
//   mkcert -cert-file dev-cert.pem -key-file dev-key.pem localhost 127.0.0.1 ::1 <your LAN IP>
//
// Absent, the server stays on HTTP exactly as before, so nobody else has to.
const certDir = fileURLToPath(new URL('./.certs/', import.meta.url))
const cert = `${certDir}dev-cert.pem`
const key = `${certDir}dev-key.pem`
const https = existsSync(cert) && existsSync(key)
  ? { cert: readFileSync(cert), key: readFileSync(key) }
  : undefined

// The FastAPI backend runs on :8010 (8000 is taken on the dev machine).
// Proxying keeps the browser on one origin, so /media photo URLs from the API
// work as-is and no API key or CORS config reaches the client.
const API = process.env.ANNRAKSHAK_API ?? 'http://127.0.0.1:8010'

interface ManifestChunk {
  file: string
  src?: string
  isEntry?: boolean
  isDynamicEntry?: boolean
  imports?: string[]
  css?: string[]
  assets?: string[]
}

/** Every file under `dir`, as site paths ('/fonts/Inter-latin.woff2'), sorted
 *  so the hash below does not depend on the order the disk lists them in. */
function filesUnder(root: string, dir: string): string[] {
  const at = join(root, dir)
  if (!existsSync(at)) return []
  return readdirSync(at, { recursive: true, withFileTypes: true })
    .filter((e) => e.isFile())
    .map((e) => `/${relative(root, join(e.parentPath, e.name)).split(sep).join('/')}`)
    .sort()
}

/** The service worker's install lists, written into dist/sw.js at build time.
 *
 *  A farmer opens the app once with signal and then stands in a field without
 *  it. Before this the worker cached a file only after the browser had asked
 *  for it through the worker, and it was registered after the first load, so
 *  Scan, Result, Weather and the rest had never been fetched: offline, every
 *  screen but Home failed to open. Now the install takes the farmer's whole
 *  app, in two parts:
 *
 *  REQUIRED: the shell (/index.html) and the entry with everything it imports
 *  statically, i.e. what opening the app at all needs. One of these failing
 *  fails the install, and the worker already on the phone stays.
 *  OPTIONAL: every farmer and Krishi screen with what each imports, the Latin
 *  fonts every screen draws with, the icons. Best effort: a screen missing
 *  offline says so; the app still opens.
 *
 *  Left out on purpose: the officer console and the public front page (not a
 *  farmer's), the eight machine-translated language tables (~25 KB gzip each;
 *  the page hands the worker the one it loaded, see main.tsx), and every field
 *  photograph. A farmer sees one crop's photo, and which copy of it depends on
 *  the phone (see fieldPhoto.ts); the worker keeps the one the phone fetched.
 *
 *  BUILD is a hash of every file on both lists and of everything under
 *  fonts/, photos/ and field/, listed or not, so a deploy that changes any of
 *  them names a new cache and the worker's activate deletes the old one. */
function precache(): Plugin {
  let outDir = ''
  return {
    name: 'annrakshak-precache',
    apply: 'build',
    configResolved(c) {
      outDir = resolve(c.root, c.build.outDir)
    },
    closeBundle() {
      const manifestPath = join(outDir, '.vite', 'manifest.json')
      const manifest = JSON.parse(readFileSync(manifestPath, 'utf8')) as Record<string, ManifestChunk>
      const seen = new Set<string>()
      const walk = (key: string, into: Set<string>) => {
        if (seen.has(key)) return
        seen.add(key)
        const c = manifest[key]
        if (!c) return
        into.add(c.file)
        c.css?.forEach((f) => into.add(f))
        c.assets?.forEach((f) => into.add(f))
        c.imports?.forEach((k) => walk(k, into))   // static imports only: a dynamic one is a choice, made below
      }
      // The entry first, so a chunk it shares with a screen is counted as the shell's.
      const shell = new Set<string>()
      const screens = new Set<string>()
      for (const [key, c] of Object.entries(manifest)) if (c.isEntry) walk(key, shell)
      for (const [key, c] of Object.entries(manifest)) {
        if (c.isDynamicEntry && /^src\/(farmer|krishi)\//.test(key)) walk(key, screens)
      }
      // Never the language tables, even if a farmer screen imports one.
      const site = (fs: Iterable<string>) => [...fs]
        .filter((f) => !/\/(bn|gu|hi|kn|ml|mr|od|pa|ta|te)-[\w-]+\.js$/.test(f))
        .map((f) => `/${f}`).sort()
      const required = ['/index.html', ...site(shell)]
      const optional = [
        ...site(screens).filter((f) => !required.includes(f)),
        '/manifest.webmanifest', '/icon-192.png', '/icon-512.png', '/favicon-64.png',
        // The two faces every farmer screen draws with. The rest (latin-ext,
        // the italic, each Indic script) are fetched only where a glyph needs
        // them, and the worker keeps them then.
        '/fonts/Inter-latin.woff2', '/fonts/InstrumentSerif-400-latin.woff2',
        // The hills behind every farmer screen's greeting (FarmerApp), and the
        // emblem in its header: without it offline the header shows a broken image.
        '/photos/hills-900.webp', '/brand/emblem-192.png',
        // The photo at the top of Scan and of Weather by day: the two screens a
        // farmer opens most, 77 KB together. The rest hide when missing.
        '/photos/leaf-dew.webp', '/photos/landscape.webp',
      ].filter((f) => existsSync(join(outDir, f)))
      const missing = required.filter((f) => !existsSync(join(outDir, f)))
      if (missing.length) throw new Error(`sw.js: required files not in the build: ${missing.join(', ')}`)

      const hashed = new Set([...required, ...optional,
        ...filesUnder(outDir, 'fonts'), ...filesUnder(outDir, 'photos'), ...filesUnder(outDir, 'field'),
        ...['/brand/emblem-192.png'].filter((f) => existsSync(join(outDir, f)))])
      const h = createHash('sha256')
      for (const f of [...hashed].sort()) h.update(f).update(readFileSync(join(outDir, f)))
      const build = h.digest('hex').slice(0, 12)

      const swPath = join(outDir, 'sw.js')
      const sw = readFileSync(swPath, 'utf8')
      const out = sw
        .replace(/^const BUILD = .*\/\/ __AR_BUILD__$/m, `const BUILD = '${build}' // __AR_BUILD__`)
        .replace(/^const REQUIRED = .*\/\/ __AR_REQUIRED__$/m, `const REQUIRED = ${JSON.stringify(required)} // __AR_REQUIRED__`)
        .replace(/^const OPTIONAL = .*\/\/ __AR_OPTIONAL__$/m, `const OPTIONAL = ${JSON.stringify(optional)} // __AR_OPTIONAL__`)
      // A worker shipped without its lists would look fine and work offline for
      // nobody: fail the build instead.
      if (!out.includes(`'${build}'`) || out.includes('const REQUIRED = [] //') || out.includes('const OPTIONAL = [] //')) {
        throw new Error('sw.js: the BUILD / REQUIRED / OPTIONAL markers were not found; the precache lists were not written')
      }
      writeFileSync(swPath, out)
      // The manifest was only for this; it need not be served.
      rmSync(join(outDir, '.vite'), { recursive: true, force: true })
      const kb = (fs: string[]) => Math.round(fs.reduce((n, f) => n + statSync(join(outDir, f)).size, 0) / 1024)
      // The line that says what a farmer's first install costs, on every build.
      this.info?.(`sw.js precache, build ${build}: required ${required.length} files ${kb(required)} KB, `
        + `optional ${optional.length} files ${kb(optional)} KB (uncompressed)`)
    },
  }
}

export default defineConfig({
  // Absolute, not './'. A relative base resolves against the current URL's
  // directory, so a cold load of a two-level route — /signup/expert,
  // /officer/queue, /app/history/12 — asked for /signup/assets/index.js, got
  // the SPA shell back as text/html, and rendered a blank page. In-app
  // navigation hid it; a refresh or a shared link did not.
  base: '/',
  plugins: [react(), precache()],
  // Read by precache() above to find every file a farmer screen needs.
  build: { manifest: true },
  // The language tables are only ever read whole (`default`). Named exports
  // wrote every string twice, once as a constant and once in the object: the
  // Hindi table was 23 KB gzip instead of 16.
  json: { namedExports: false, stringify: true },
  server: {
    https,
    // slim.sh maps https://annrakshak.test → localhost:5173; Vite 8 refuses
    // requests whose Host header isn't localhost unless it is allow-listed.
    allowedHosts: ['annrakshak.test', '.slim.show'],
    proxy: {
      '/api': { target: API, ws: true }, // ws: the live field walk streams frames over a WebSocket
      '/media': API,
      '/samples': API,
      '/health': API,
    },
  },
})
