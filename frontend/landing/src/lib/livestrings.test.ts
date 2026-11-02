import { describe, expect, it } from 'vitest'
import { LANGS } from './i18n'

/** The screen's own source, so the list of strings it asks for cannot drift
 *  away from the code that asks for them. */
const SOURCE = import.meta.glob('../farmer/screens/Live.tsx', {
  eager: true, query: '?raw', import: 'default',
}) as Record<string, string>

const TABLES = import.meta.glob('../locales/*.json', {
  eager: true, import: 'default',
}) as Record<string, Record<string, string>>

const used = [...Object.values(SOURCE)[0].matchAll(/\bt\('([A-Za-z0-9_]+)'\)/g)].map((m) => m[1])

describe('the live call speaks every language the app offers', () => {
  it('reads the screen and finds the strings it asks for', () => {
    expect(used.length).toBeGreaterThan(20)
  })

  // A missing key is not an error anywhere: the lookup falls back to English and
  // then to the key itself, so the only sign of one is a farmer who chose Tamil
  // reading English on the screen that talks the most. Nothing else catches it.
  for (const { code } of LANGS.filter((l) => !['en', 'hi', 'mr'].includes(l.code))) {
    it(`has every live-call string in ${code}`, () => {
      const table = TABLES[`../locales/${code}.json`]
      expect(table, `no locale file for ${code}`).toBeTruthy()
      expect(used.filter((k) => !table[k]?.trim())).toEqual([])
    })
  }
})
