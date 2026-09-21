// Desktop grid shared by the farmer app's tab screens. Below lg none of these
// classes do anything, so the phone layout is whatever each screen stacks.
// Every screen splits the same 12 columns 8 | 4, so the side column's edge
// sits in the same place on Home, Weather, Scan, Spray and Alerts.

/** Two-column row: main on the left, side column on the right. */
export const SPLIT = 'lg:grid lg:grid-cols-12 lg:gap-8 lg:items-start lg:space-y-0'
export const MAIN = 'lg:col-span-8'
export const SIDE = 'lg:col-span-4'

/** A row whose cards stretch to one height. */
export const ROW = 'lg:grid lg:grid-cols-12 lg:gap-8 lg:items-stretch lg:space-y-0'

/** Section label used on desktop to give each column a clear heading. */
export const EYEBROW = 'text-[11px] font-semibold uppercase tracking-[0.12em] text-soil-dark/45'
