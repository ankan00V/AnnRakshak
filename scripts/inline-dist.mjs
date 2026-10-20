import { readFileSync, writeFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const dist = resolve(dirname(fileURLToPath(import.meta.url)), '../frontend/landing/dist')
let html = readFileSync(resolve(dist, 'index.html'), 'utf8')

html = html.replace(
  /<script type="module"[^>]*src="([^"]+)"[^>]*><\/script>/,
  (_, src) => `<script type="module">${readFileSync(resolve(dist, src.replace(/^\//, '')), 'utf8')}</script>`,
)
html = html.replace(
  /<link rel="stylesheet"[^>]*href="([^"]+)"[^>]*>/,
  (_, href) => `<style>${readFileSync(resolve(dist, href), 'utf8')}</style>`,
)

writeFileSync(resolve(dist, 'index-single.html'), html)
console.log('wrote dist/index-single.html,', html.length, 'bytes')
