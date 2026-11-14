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
  samples: { src: '/demo/samples-en.webp' },
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
  home: { x: 0.5, y: 0.93 },       // Scan, raised in the middle of the bottom bar
  samples: { x: 0.5, y: 0.517 },   // false smut, an untagged ICAR sample
  framed: { x: 0.5, y: 0.817 },    // Check this photo
  verdict: { x: 0.647, y: 0.044 }, // the language button in the header
  lang: { x: 0.265, y: 0.614 },    // मराठी
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
  await a.wait(1400)

  // Down to the held-out ICAR photographs — the app's own words for them are
  // "never used in training".
  await a.set({ at: 'samples' })
  await a.wait(1000)
  await tap('samples')
  await a.set({ at: 'framed' })
  await a.wait(1300)

  // The press the product hangs on. What follows is the gate, not a spinner.
  await tap('framed')
  await a.set({ busy: true })
  await a.wait(1400)
  await a.set({ at: 'verdict', busy: false })
  await a.wait(2600)

  // Down the answer: what not to do, then the cheapest thing that works, then
  // when to call an expert and the number to call. This is the part a
  // plant-identification app has nothing to show for.
  await a.set({ at: 'advice' })
  await a.wait(2800)
  await a.set({ at: 'expert' })
  await a.wait(2600)

  // And the same answer in her own language, which is one tap away. On a
  // phone the header scrolls with the page, so it is back at the top first.
  await a.set({ at: 'verdict' })
  await a.wait(900)
  await tap('verdict')
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
      // Tall enough for the whole phone and no taller: a 306-wide iPhone
      // stands 662, and dead air around it reads as a plate.
      width={430}
      height={690}
      compact={{ below: 440, width: 358, height: 640 }}
      initial={START}
      // The frame most people ever see — a thumbnail, reduced motion, a
      // screenshot in a deck — is the one carrying the answer.
      poster={{ at: 'verdict' }}
      script={script}
      cursor={{ at: REST, style: 'touch' }}
      className="sd"
    >
      {(s, _rect, layout) => {
        const width = layout === 'compact' ? 288 : 306
        return (
          <>
            <Phone
              width={width}
              // The app's top is a light sky now, so the clock and battery
              // are drawn dark over it, as the phone itself would.
              // What a real device shows around the app: its header colour
              // runs up behind the clock and battery, and the bottom bar's
              // own white runs down behind the home indicator. Measured off
              // the captures (#d3e3ef, the sky over the hills, and #fffefe)
              // so the seams disappear.
              wallpaper="linear-gradient(#d3e3ef 0 62px, #fffefe 62px)"
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
