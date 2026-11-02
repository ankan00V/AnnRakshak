import { Stage, Phone, type Act } from './kit'
import './scan-demo.css'

/** The product, doing the thing it claims, in the hero.
 *
 *  Every frame here is a photograph of the real app, taken by
 *  `scripts/capture-demo.mjs` driving it at phone width: the farmer's home
 *  screen, the camera prompt, a held-out ICAR photograph run through the real
 *  pipeline, and the three screens of the answer that comes back. Nothing is
 *  drawn or mocked. The
 *  first cut of this was an illustration of the app, and an illustration can
 *  quietly flatter — this cannot, because when the app changes the capture is
 *  re-run and the hero changes with it.
 *
 *  It replaced an 11.4 MB video hot-linked from a generation service's CDN.
 *  The whole frame set is 290 KB, served from this origin, and it shows the
 *  Grad-CAM, the confidence against the ask and advise thresholds, the
 *  district adjustment, what else was considered, what not to do, the field
 *  practice before the chemical, and the number to call — the things that
 *  distinguish this from a plant-identification app.
 *
 *  Built on the Stageshow kit (MIT; `KIT-LICENSE.txt`).
 */

/** A frame. Each one is a screen of the app as it really renders, so the
 *  verdict is three photographs rather than one tall one travelled by
 *  transform: a full-page capture bakes the fixed bottom bar into the middle
 *  of the image, and a bar floating mid-screen reads as a bug in the product.
 */
type Shot = { src: string }

const FRAMES = {
  home: { src: '/demo/home-en.webp' },
  scan: { src: '/demo/scan-en.webp' },
  framed: { src: '/demo/framed-en.webp' },
  verdict: { src: '/demo/result-en-0.webp' },
  advice: { src: '/demo/result-en-1.webp' },
  expert: { src: '/demo/result-en-2.webp' },
  lang: { src: '/demo/lang-open.webp' },
  marathi: { src: '/demo/result-mr.webp' },
} satisfies Record<string, Shot>

type Key = keyof typeof FRAMES
type S = { at: Key; busy?: boolean }

const START: S = { at: 'home' }
const REST = { x: 300, y: 500 }

/** Where the cursor goes, as a share of the screen: these are taps on a
 *  photograph, so they are placed against what the photograph shows. */
const TAPS: Partial<Record<Key, { x: number; y: number }>> = {
  home: { x: 0.5, y: 0.945 },    // Scan, in the bottom bar
  scan: { x: 0.22, y: 0.66 },    // the first ICAR sample
  framed: { x: 0.5, y: 0.71 },   // the Scan button under the framed leaf
  expert: { x: 0.74, y: 0.037 }, // the language pill in the header
  lang: { x: 0.28, y: 0.49 },    // मराठी
}

const script = async (a: Act<S>) => {
  const tap = async (at: Key) => {
    if (TAPS[at]) await a.click(`tap-${at}`)
    else await a.wait(200)
  }

  await a.wait(1100)

  // Her field, then the one button the home screen is built around.
  await tap('home')
  await a.set({ at: 'scan' })
  await a.wait(1200)

  // A held-out ICAR photograph — the app's own words for them are "real
  // photographs the model has been scored on".
  await tap('scan')
  await a.set({ at: 'framed' })
  await a.wait(1300)

  // The press the product hangs on. What follows is the gate, not a spinner.
  await tap('framed')
  await a.set({ busy: true })
  await a.wait(1400)
  await a.set({ at: 'verdict', busy: false })
  await a.wait(2600)

  // Down the answer: what not to do, then the cheapest thing that works, then
  // who to call and when it will ask her how it went. This is the part a
  // plant-identification app has nothing to show for.
  await a.set({ at: 'advice' })
  await a.wait(2800)
  await a.set({ at: 'expert' })
  await a.wait(2600)

  // And the same answer in her own language, which is one tap away.
  await tap('expert')
  await a.set({ at: 'lang' })
  await a.wait(1400)
  await tap('lang')
  await a.set({ at: 'marathi' })
  await a.wait(3200)

  // Back where it began.
  await a.set({ at: 'home' })
  await a.move(REST)
  await a.wait(700)
}

export default function ScanDemo() {
  return (
    <Stage<S>
      // Tall enough for the whole phone: a 330-wide iPhone stands 714, and a
      // product shot cut off at the knee is not a product shot.
      width={430}
      height={736}
      compact={{ below: 440, width: 358, height: 672 }}
      initial={START}
      // The frame most people ever see — a thumbnail, reduced motion, a
      // screenshot in a deck — is the one carrying the answer.
      poster={{ at: 'verdict' }}
      script={script}
      cursor={{ at: REST, style: 'touch' }}
      className="sd"
    >
      {(s, _rect, layout) => {
        const width = layout === 'compact' ? 300 : 330
        return (
          <>
            <div className="sd-wash" />
            <Phone
              width={width}
              dark
              // What a real device shows around the app: its header colour
              // runs up behind the clock and battery, and the bottom bar's
              // own white runs down behind the home indicator. Measured off
              // the captures (#1f3d2c and #f5f5f5) so the seams disappear.
              wallpaper="linear-gradient(#1f3d2c 0 62px, #f5f5f5 62px)"
              className="sd-phone"
            >
              <div className="sd-screen">
                {/* Both frames stay mounted so one dissolves into the other
                    rather than the screen blinking white between them. */}
                {Object.entries(FRAMES).map(([key, f]) => (
                  <img
                    key={key}
                    src={f.src}
                    alt=""
                    className="sd-shot"
                    data-on={key === s.at || undefined}
                    loading={key === 'home' ? 'eager' : 'lazy'}
                    draggable={false}
                  />
                ))}

                {/* Tap targets over the photograph, so the cursor lands on the
                    control the frame actually shows. */}
                {Object.entries(TAPS).map(([key, t]) =>
                  t ? (
                    <span
                      key={key}
                      data-target={`tap-${key}`}
                      className="sd-tap"
                      style={{ left: `${t.x * 100}%`, top: `${t.y * 100}%` }}
                    />
                  ) : null,
                )}

                {s.busy && (
                  <span className="sd-busy">
                    <span className="sd-busy__pulse" />
                  </span>
                )}
              </div>
            </Phone>
          </>
        )
      }}
    </Stage>
  )
}
