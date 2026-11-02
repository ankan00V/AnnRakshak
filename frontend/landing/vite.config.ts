import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

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

export default defineConfig({
  // Absolute, not './'. A relative base resolves against the current URL's
  // directory, so a cold load of a two-level route — /signup/expert,
  // /officer/queue, /app/history/12 — asked for /signup/assets/index.js, got
  // the SPA shell back as text/html, and rendered a blank page. In-app
  // navigation hid it; a refresh or a shared link did not.
  base: '/',
  plugins: [react()],
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
