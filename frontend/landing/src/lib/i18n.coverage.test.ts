import { describe, expect, it } from 'vitest'
import { LANGS } from './i18n'

const SOURCES = import.meta.glob('../**/*.{ts,tsx}', {
  eager: true, query: '?raw', import: 'default',
}) as Record<string, string>

const TABLES = import.meta.glob('../locales/*.json', {
  eager: true, import: 'default',
}) as Record<string, Record<string, string>>

/** The English table, read out of i18n.ts itself. Asserting against this rather
 *  than against the keys screens are seen to ask for is the stronger test: it
 *  holds however a key is reached, including the ones built at runtime from a
 *  map or a template, which no scan of the source can see. */
const I18N_SRC = import.meta.glob('./i18n.ts', {
  eager: true, query: '?raw', import: 'default',
}) as Record<string, string>

const english = (() => {
  const src = Object.values(I18N_SRC)[0] ?? ''
  const from = src.indexOf('const en = {')
  const to = src.indexOf('const hi')
  const block = from >= 0 && to > from ? src.slice(from, to) : ''
  return new Set([...block.matchAll(/^ {2}'?([A-Za-z0-9_+]+)'?:/gm)].map((m) => m[1]))
})()

/** Keys asked for with a literal, used to catch a screen asking for a key that
 *  does not exist at all — a typo renders the key name to the farmer. */
const asked = new Set<string>()
for (const [path, src] of Object.entries(SOURCES)) {
  if (path.includes('/locales/') || /\.test\.tsx?$/.test(path)) continue
  for (const m of src.matchAll(/\bt\('([A-Za-z0-9_]+)'\)/g)) asked.add(m[1])
}

/** English, Hindi and Marathi are authored in i18n.ts. The rest are files, and a
 *  key missing from one is invisible: the lookup falls back to English and the
 *  farmer who chose Tamil simply reads English. Nothing else catches that. */
const SHIPPING = LANGS.map((l) => l.code).filter((c) => !['en', 'hi', 'mr'].includes(c))

describe('every string the app offers exists in every language it offers', () => {
  it('read the English table and the screens', () => {
    expect(english.size).toBeGreaterThan(600)
    expect(asked.size).toBeGreaterThan(200)
  })

  it('asks for no string that was never written', () => {
    expect([...asked].filter((k) => !english.has(k)).sort()).toEqual([])
  })

  for (const code of SHIPPING) {
    it(`speaks ${code}`, () => {
      const table = TABLES[`../locales/${code}.json`]
      expect(table, `no locale file for ${code}`).toBeTruthy()
      const missing = [...english].filter((k) => !table[k]?.trim()).sort()
      expect(missing, `${code} falls back to English for these`).toEqual([])
    })
  }
})
