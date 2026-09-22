// The app tour, step by step. Each step points at an element tagged
// data-tour="<target>" (none: a centred card), shows tour_<id>_t / tour_<id>_b
// and plays public/tour/<lang>/<id>.mp3 (backend/make_tour_audio.py — keep
// the ids in step with its STEPS).
//
// `tap`: the farmer may tap the real thing and the tour goes on from there
// (Spray check and Alerts open their screens). Cards on Home are shown, not
// opened, so a stray tap never takes the tour off the page it is explaining.

export interface TourStep {
  id: string
  target?: string
  side?: 'top' | 'right' | 'bottom' | 'left'
  tap?: boolean
}

export const TOUR_STEPS: TourStep[] = [
  { id: 'welcome' },
  { id: 'farm', target: 'farm', side: 'bottom' },
  { id: 'weather', target: 'weather', side: 'bottom' },
  { id: 'live', target: 'live', side: 'top' },
  { id: 'scan', target: 'scan', side: 'top' },
  { id: 'checks', target: 'checks', side: 'top' },
  { id: 'spray', target: 'nav-spray', tap: true },
  { id: 'alerts', target: 'nav-alerts', tap: true },
  { id: 'krishi', target: 'krishi', side: 'left' },
  { id: 'lang', target: 'lang', side: 'bottom' },
  { id: 'done' },
]

/** Seen or declined by this account on this device: not offered again. */
export const tourSeenKey = (userId: number | undefined) => `ar.tour.v1:${userId ?? 'guest'}`
export const TOUR_MUTED_KEY = 'ar.tour.muted'
/** Accounts this new are offered the tour when they first open the app. */
export const NEW_ACCOUNT_DAYS = 7
/** Pause after a step's voice ends before the tour moves on. */
export const AFTER_VOICE_MS = 900
/** Without sound, a step stays up for its reading time: ~0.42 s a word, 4 s at least. */
export const readingMs = (text: string) => Math.max(4000, text.split(/\s+/).length * 420)
