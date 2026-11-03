import Reveal from '../ui/Reveal'

/** The problem, in three sentences a farmer would say out loud.
 *  The pesticide figure is the sum of every state MoSPI publishes for 2023-24
 *  (DPPQS via eSankhyiki) — the app is for the country, so the number is the
 *  country's, not the one state the problem statement came from. */
const FACTS = [
  { figure: '3–7 days', rest: 'pass between the first sick leaf and the first spot anyone notices.' },
  { figure: 'One officer', rest: 'for thousands of fields. Help usually arrives after the damage.' },
  { figure: '79,423 tonnes', rest: 'of pesticide sprayed in a year. A wrong spray costs twice — the money, and the crop.', source: 'MoSPI eSankhyiki (DPPQS), 2023-24' },
]

export default function Problem() {
  return (
    <section id="problem" className="w-full bg-cream text-soil-dark">
      <div className="max-w-6xl mx-auto px-6 md:px-12 py-14 sm:py-20 md:py-24">
        <Reveal className="max-w-3xl">
          <h2 className="font-instrument-serif text-[2rem] sm:text-5xl md:text-[3.5rem] leading-[1.05] text-balance">
            By the time you can see it, it has already spread.
          </h2>
        </Reveal>

        {/* Three sentences, each led by its number, rather than a row of
            big figures with small labels under them: read in order they say
            the problem the way a farmer would. */}
        <ul className="mt-8 sm:mt-12 grid gap-6 md:grid-cols-3 md:gap-10">
          {FACTS.map(({ figure, rest, source }, i) => (
            <Reveal key={figure} delay={i * 80}>
              <li className="border-t border-soil-dark/15 pt-5">
                <p className="font-instrument-serif text-[1.5rem] md:text-[1.75rem] leading-snug text-pretty">
                  <span className="text-leaf">{figure}</span> {rest}
                </p>
                {source && <p className="mt-2 text-xs text-soil-dark/60">Source: {source}</p>}
              </li>
            </Reveal>
          ))}
        </ul>
      </div>
    </section>
  )
}
