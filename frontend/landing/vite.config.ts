import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

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
