import { defineConfig, mergeConfig } from 'vitest/config'
import base from './vite.config.ts'

// The app's own Vite config plus a DOM to render into, kept separate so the
// production build never carries test settings.
//
// happy-dom rather than jsdom: under jsdom 29 the environment hands back a
// bare {} for localStorage, so anything asserting what this browser remembers
// would have passed without remembering anything.
export default mergeConfig(base, defineConfig({
  test: {
    environment: 'happy-dom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    restoreMocks: true,
  },
}))
