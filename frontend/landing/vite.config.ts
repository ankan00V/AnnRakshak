import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The FastAPI backend runs on :8010 (8000 is taken on the dev machine).
// Proxying keeps the browser on one origin, so /media photo URLs from the API
// work as-is and no API key or CORS config reaches the client.
const API = process.env.ANNRAKSHAK_API ?? 'http://127.0.0.1:8010'

export default defineConfig({
  base: './',
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
