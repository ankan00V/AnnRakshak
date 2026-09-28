import Reveal from '../ui/Reveal'

/** Three rows, not three cards: each one pairs what it costs with why.
 *  The pesticide figure is the state's own (MoSPI/DPPQS via eSankhyiki). */
const ROWS = [
  {
    figure: '3–7 days',
    unit: 'lost before symptoms are obvious',
    line: 'A leaf spot is days old by the time it is unmistakable. Treatment that would have cost one careful spray now costs a season.',
  },
  {
    figure: 'One officer',
    unit: 'for thousands of fields',
    line: 'Extension staff cover more land than anyone can walk. Most crops get expert eyes only after the damage is already visible from the road.',
  },
  {
    figure: '8,719 t',
    unit: 'of chemical pesticide · Maharashtra, 2023-24',
    line: 'Third-highest in India. A wrong guess at the spray shop is paid for twice — once at the counter, again in the yield it never saved.',
    source: 'MoSPI eSankhyiki (DPPQS)',
  },
]

export default function Problem() {
  return (
    <section id="problem" className="w-full bg-cream text-soil-dark">
      <div className="max-w-6xl mx-auto px-6 md:px-12 py-20 md:py-28">
        <Reveal className="grid gap-8 lg:grid-cols-12 lg:gap-16 lg:items-end">
          <h2 className="lg:col-span-7 font-instrument-serif text-[2rem] sm:text-5xl md:text-[3.5rem] leading-[1.05] text-balance">
            By the time you can see it,
            <span className="block text-soil-dark/70">it has already spread.</span>
          </h2>
          <p className="lg:col-span-5 text-base font-light leading-relaxed text-soil-dark/80 text-pretty">
            Crop disease announces itself quietly and then moves fast. The gap between the first
            infected leaf and the first phone call is where a harvest is lost.
          </p>
        </Reveal>

        <div className="mt-14 md:mt-20 border-t border-soil-dark/15">
          {ROWS.map(({ figure, unit, line, source }, i) => (
            <Reveal key={figure} delay={i * 90}>
              <div className="group grid gap-3 md:grid-cols-12 md:gap-8 items-baseline border-b border-soil-dark/15 py-7 md:py-9 transition-colors duration-300 hover:bg-soil-dark/[0.03]">
                <div className="md:col-span-5">
                  <p className="font-instrument-serif text-4xl md:text-5xl leading-none text-ochre">
                    {figure}
                  </p>
                  <p className="mt-2 text-xs md:text-sm font-medium text-soil-dark/70">{unit}</p>
                </div>
                <p className="md:col-span-7 text-sm md:text-base font-light leading-relaxed text-soil-dark/80 text-pretty">
                  {line}
                  {source && (
                    <span className="block mt-2 text-xs text-soil-dark/70">Source: {source}</span>
                  )}
                </p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}
