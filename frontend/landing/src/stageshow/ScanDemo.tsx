import { Stage, Phone, Bar, Avatar, Collapse, type Act } from './kit'
import './scan-demo.css'

/** The promise of the whole app, in twelve seconds: a farmer photographs a
 *  sick leaf and is told what it is, in Marathi, with the first thing to do.
 *
 *  This replaced an eleven-megabyte video hot-linked from somebody else's CDN.
 *  It is a few kilobytes of React, it tells every visitor's browser nothing
 *  about them, and — unlike stock footage of a field — it is the product.
 *
 *  Built with the Stageshow kit (MIT, `KIT-LICENSE.txt`). Nothing here is
 *  another company's interface: the chrome, the words and the colours are
 *  AnnRakshak's own, which is also what makes it worth showing.
 */

type S = {
  /** home → the camera is up → the answer is in */
  phase: 'home' | 'shot' | 'reading' | 'answer'
}

const START: S = { phase: 'home' }
const REST = { x: 300, y: 470 }

const script = async (a: Act<S>) => {
  await a.wait(900)
  // The farmer reaches for the one button the home screen is built around.
  await a.click('scan')
  await a.set({ phase: 'shot' })
  await a.wait(1100)

  // The shutter. What follows is the gate thinking, not a spinner for show.
  await a.click('shutter')
  await a.set({ phase: 'reading' })
  await a.wait(1500)

  // The payoff, and it holds: the name, how sure, and the first thing to do.
  await a.set({ phase: 'answer' })
  await a.wait(3200)

  // The loop has a cause: she closes the answer and the camera comes down.
  await a.click('done')
  await a.set({ phase: 'home' })
  await a.move(REST)
  await a.wait(500)
}

/** The leaf, drawn rather than photographed: a lesion on a rice blade. A real
 *  photograph here would be somebody's copyright and a quarter of a megabyte. */
function Leaf({ lesion }: { lesion?: boolean }) {
  return (
    <svg className="sd-leaf" viewBox="0 0 220 300" aria-hidden>
      <defs>
        <linearGradient id="sd-blade" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#4f7f45" />
          <stop offset="100%" stopColor="#2f5c32" />
        </linearGradient>
      </defs>
      <path d="M110 12c46 54 66 120 58 186-4 36-22 68-58 90-36-22-54-54-58-90C44 132 64 66 110 12z"
            fill="url(#sd-blade)" />
      <path d="M110 24v258" stroke="#8fbf7a" strokeWidth="2.5" opacity=".55" />
      {[70, 110, 150, 190, 230].map((y) => (
        <g key={y} stroke="#8fbf7a" strokeWidth="1.3" opacity=".35">
          <path d={`M110 ${y} C 88 ${y + 6}, 74 ${y + 16}, 64 ${y + 30}`} fill="none" />
          <path d={`M110 ${y} C 132 ${y + 6}, 146 ${y + 16}, 156 ${y + 30}`} fill="none" />
        </g>
      ))}
      {lesion && (
        <g className="sd-leaf__lesion">
          <ellipse cx="92" cy="140" rx="15" ry="27" fill="#c8a24a" opacity=".92" transform="rotate(-12 92 140)" />
          <ellipse cx="92" cy="140" rx="7" ry="16" fill="#e8dcc0" transform="rotate(-12 92 140)" />
          <ellipse cx="133" cy="196" rx="11" ry="20" fill="#b98f3e" opacity=".85" transform="rotate(10 133 196)" />
          <ellipse cx="133" cy="196" rx="5" ry="11" fill="#e8dcc0" transform="rotate(10 133 196)" />
        </g>
      )}
    </svg>
  )
}

export default function ScanDemo() {
  return (
    <Stage<S>
      width={430}
      height={560}
      compact={{ below: 440, width: 358, height: 520 }}
      initial={START}
      // Most people only ever see this frame — a thumbnail, reduced motion, a
      // screenshot in a deck. So it is the answer, not a beat on the way there.
      poster={{ phase: 'answer' }}
      script={script}
      cursor={{ at: REST, style: 'touch' }}
      className="sd"
    >
      {(s, _rect, layout) => {
        const open = s.phase !== 'home'
        return (
          <>
            <div className="sd-wash" />
            <Phone width={layout === 'compact' ? 322 : 352} className="sd-phone">
              {/* The home screen stays mounted under the camera, so coming
                  back is the camera leaving rather than a new screen arriving. */}
              <div className="sd-home" data-back={open || undefined}>
                <header className="sd-home__head">
                  <span className="sd-home__who">
                    <span className="sd-home__place">सुनीता · भंडारा</span>
                    <span className="sd-home__crop">भात · ७८ दिवस · फुलोरा</span>
                  </span>
                  <Avatar name="Sunita" size={34} />
                </header>

                <section className="sd-alert">
                  <span className="sd-alert__dot" />
                  <span className="sd-alert__body">
                    <span className="sd-alert__title">आजची शेत तपासणी</span>
                    <Bar w={126} h={7} r={4} tone={3} />
                    <Bar w={92} h={7} r={4} tone={3} />
                  </span>
                </section>

                <button className="sd-scan" data-target="scan" data-cursor="pointer">
                  <span className="sd-scan__ring" />
                  <span className="sd-scan__label">फोटो काढा</span>
                </button>

                {/* Past checks, filling the screen to its foot. Two rows left a
                    void under them, which reads as a screen still being built
                    rather than a quiet one. Filler, so the eye stays on the
                    alert and the button above. */}
                <div className="sd-rows">
                  {[124, 104, 136, 92, 118].map((w, i) => (
                    <div key={w} className="sd-row">
                      <span className="sd-row__thumb" />
                      <span className="sd-row__text">
                        <Bar w={w} h={8} r={4} tone={2} />
                        <Bar w={w - 46} h={6} r={3} tone={3} />
                      </span>
                      <span className="sd-row__when">
                        <Bar w={i % 2 ? 22 : 26} h={6} r={3} tone={3} />
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* The camera, and then the answer over it. */}
              <div className="sd-cam" data-on={open || undefined}>
                <Leaf lesion={s.phase !== 'home'} />
                <div className="sd-cam__grid" aria-hidden />

                {s.phase === 'shot' && (
                  <button className="sd-shutter" data-target="shutter" data-cursor="pointer" aria-label="shutter">
                    <span className="sd-shutter__ring" />
                  </button>
                )}

                {s.phase === 'reading' && (
                  <div className="sd-reading">
                    <span className="sd-reading__pulse" />
                    <span>तपासत आहे…</span>
                  </div>
                )}

                <Collapse open={s.phase === 'answer'}>
                  <div className="sd-answer">
                    <span className="sd-answer__grab" aria-hidden />
                    <p className="sd-answer__name">करपा (ब्लास्ट)</p>
                    <p className="sd-answer__sure">
                      ९४% खात्री
                      <span className="sd-answer__gate">सल्ला देण्याइतकी</span>
                    </p>
                    <p className="sd-answer__do">
                      <span className="sd-answer__tick" aria-hidden />
                      आजच पाणी कमी करा; नत्र खत थांबवा
                    </p>
                    <button className="sd-answer__done" data-target="done" data-cursor="pointer">
                      ठीक आहे
                    </button>
                  </div>
                </Collapse>
              </div>
            </Phone>
          </>
        )
      }}
    </Stage>
  )
}
