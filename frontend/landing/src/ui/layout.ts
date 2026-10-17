// The desktop grid both consoles are laid out on. Below lg none of these
// classes do anything, so the phone layout is whatever each screen stacks.
//
// It started in the farmer app, which is the half that looked composed: every
// screen splits the same 12 columns 8 | 4, so a side column's edge sits in the
// same place from screen to screen. The officer console had a different grid
// per page — 1.3fr | 1fr on one, 1fr | 1fr on the next, plain halves on a
// third — which is most of why it read as messier at a glance.

/** Two-column row: main on the left, side column on the right. */
export const SPLIT = 'lg:grid lg:grid-cols-12 lg:gap-8 lg:items-start lg:space-y-0'
export const MAIN = 'lg:col-span-8'
export const SIDE = 'lg:col-span-4'

/** A row whose cards stretch to one height. */
export const ROW = 'lg:grid lg:grid-cols-12 lg:gap-8 lg:items-stretch lg:space-y-0'

/** Section label used on desktop to give each column a clear heading. */
export const EYEBROW = 'text-[11px] font-semibold uppercase tracking-[0.12em] text-soil-dark/45'
