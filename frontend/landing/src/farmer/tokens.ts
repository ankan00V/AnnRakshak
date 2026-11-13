/** Shared values for the farmer's tab screens (the components are in ui.tsx). */

/** A white card, the shape every block on a tab screen shares. */
export const PANEL = 'rounded-[28px] bg-white shadow-[0_10px_30px_-18px_rgba(43,29,18,0.35)] ring-1 ring-soil-dark/[0.06]'

/** Open-Meteo's WMO weather code, as the key of the words for it. */
export function wmoKey(code: number | null): string {
  if (code == null) return 'wmo_partly'
  if (code === 0) return 'wmo_clear'
  if (code <= 2) return 'wmo_partly'
  if (code === 3) return 'wmo_overcast'
  if (code === 45 || code === 48) return 'wmo_fog'
  if (code >= 51 && code <= 57) return 'wmo_drizzle'
  if (code >= 61 && code <= 67) return 'wmo_rain'
  if (code >= 71 && code <= 77) return 'wmo_snow'
  if (code >= 80 && code <= 86) return 'wmo_showers'
  if (code >= 95) return 'wmo_thunder'
  return 'wmo_partly'
}

/** Risk level as a row tint and a pill. */
export const RISK = {
  high: { row: 'bg-[#fdf0ed]', pill: 'bg-[#f9dcd5] text-[#9a2f17]', key: 'riskHigh' },
  medium: { row: 'bg-[#fbf5ea]', pill: 'bg-[#f6e6c4] text-[#7a4f12]', key: 'riskMedium' },
  low: { row: 'bg-[#f1f6ec]', pill: 'bg-[#dcebd0] text-[#2f5a24]', key: 'riskLow' },
} as const

/** Where a photo check stands, as a pill colour. */
export const STATUS_PILL = {
  leaf: 'bg-[#e3efd9] text-[#2f5a24]',
  sky: 'bg-sky-100 text-sky-800',
  ochre: 'bg-[#f6e6c4] text-[#7a4f12]',
  neutral: 'bg-soil-dark/5 text-soil-dark/80',
} as const

/** A text box or select on a farmer's screen: large, tinted, green when in use. */
export const FIELD = 'mt-1.5 w-full min-h-[48px] rounded-2xl bg-[#f5f7f1] px-4 text-[16px] ring-1 ring-soil-dark/10 placeholder:text-soil-dark/55 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#4b8b3b]'
/** The label above one. */
export const LABEL = 'block text-[14px] font-medium text-soil-dark/80'
/** The one thing to press. */
export const PRIMARY = 'flex min-h-[52px] w-full items-center justify-center gap-2 rounded-full bg-[#2f6a39] text-[16px] font-semibold text-white transition-colors hover:bg-[#2a5f33] disabled:opacity-50'
/** Anything else to press. */
export const SECONDARY = 'flex min-h-[48px] items-center justify-center gap-2 rounded-full bg-[#eef3e6] px-5 text-[15px] font-semibold text-leaf-deep ring-1 ring-[#4b8b3b]/15 transition-colors hover:bg-[#e6eedb] disabled:opacity-50'
