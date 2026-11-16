import Reveal from '../ui/Reveal'
import FootageBackdrop from '../ui/FootageBackdrop'

/** One rice field's season, in the team's own footage from the ground (and a
 *  still for tillering, which was not filmed), joined into a timeline: the
 *  field is watched from the day it is sown, not from the day a spot shows.
 *
 *  Day 41 is tillering in the rice calendar (days 26–55), which is the stage
 *  in the photograph. Day 126 is the harvest the phenology model predicted
 *  for a real rice field sown on 13 July, from that field's own weather. */
const SEASON = [
  { video: '/footage/new-season.mp4', img: '/footage/new-season-poster.webp', pos: 'object-[62%_55%]', day: 'Day 1', stage: 'Sowing', line: 'The day it goes in, the count starts.' },
  { video: '', img: '/field/rice.webp', pos: 'object-center', day: 'Day 41', stage: 'Tillering', line: 'Told where to look, before anything shows.' },
  { video: '/footage/field.mp4', img: '/footage/field-poster.webp', pos: 'object-[52%_50%]', day: 'Day 126', stage: 'Harvest', line: 'A harvest date worked out, not guessed.' },
  { video: '/footage/baling.mp4', img: '/footage/baling-poster.webp', pos: 'object-[45%_60%]', day: '', stage: 'After harvest', line: 'The season closes, and is kept.' },
]

export default function InTheField() {
  return (
    <section id="in-the-field" className="w-full bg-[#f6f1e6] text-[#1f3a26]">
      <div className="mx-auto grid max-w-[1720px] gap-10 px-6 py-14 md:px-12 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,3fr)] lg:items-center lg:gap-[3vw] lg:px-[7vw] lg:py-[clamp(48px,4vw,80px)]">
        <Reveal>
          <h2 className="font-display text-[34px] leading-[1.08] tracking-[-0.01em] text-balance lg:text-[clamp(28px,2.35vw,46px)]">
            By the time you can see it, it has already spread.
          </h2>
          <p className="mt-4 text-[15px] leading-relaxed text-[#3d4a40] text-pretty lg:mt-[1.2vw] lg:text-[clamp(13px,0.95vw,17px)]">
            A leaf disease spreads for 3–7 days before anyone notices. So AnnRakshak watches each
            field from the day it is sown.
          </p>
        </Reveal>

        {/* The season as a timeline: a line runs behind the cards and shows
            in the gaps, with a dot between each stage and the next. */}
        <Reveal delay={80}>
          <ol className="relative grid grid-cols-2 gap-4 lg:grid-cols-4 lg:gap-[1.6vw]">
            <span aria-hidden className="absolute inset-x-0 top-[78%] hidden h-px bg-[#c9b48a] lg:block" />
            {SEASON.map(({ video, img, pos, day, stage, line }, i) => (
              <li key={stage} className={`relative ${i < SEASON.length - 1 ? 'lg:after:absolute lg:after:-right-[calc(0.8vw+5px)] lg:after:top-[78%] lg:after:h-2.5 lg:after:w-2.5 lg:after:-translate-y-1/2 lg:after:rounded-full lg:after:border-2 lg:after:border-[#f6f1e6] lg:after:bg-[#b08a3c] lg:after:content-[""]' : ''}`}>
                <figure className="relative z-10 h-full overflow-hidden rounded-[20px] bg-white shadow-[0_18px_40px_-28px_rgba(43,29,18,0.55)] ring-1 ring-black/[0.05]">
                  <div className="relative aspect-[4/3] w-full overflow-hidden bg-[#dfe6d3]">
                    {video
                      ? <FootageBackdrop src={video} poster={img} objectClass={pos} scrim={null} />
                      : <img src={img} alt="" loading="lazy" decoding="async" className={`absolute inset-0 h-full w-full object-cover ${pos}`} />}
                  </div>
                  <figcaption className="px-4 pb-4 pt-3 lg:px-[1.1vw] lg:pb-[1.1vw] lg:pt-[0.8vw]">
                    <p className="text-[14px] font-semibold lg:text-[clamp(13px,0.95vw,17px)]">
                      {day && <span className="text-[#9a6210]">{day} · </span>}{stage}
                    </p>
                    <p className="mt-1 text-[13px] leading-snug text-[#55615a] lg:text-[clamp(12px,0.85vw,15px)]">{line}</p>
                  </figcaption>
                </figure>
              </li>
            ))}
          </ol>
        </Reveal>
      </div>
    </section>
  )
}
