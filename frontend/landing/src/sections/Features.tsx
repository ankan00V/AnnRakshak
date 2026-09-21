import { Ban, Bug, CloudRain, Gauge, Languages, Map, UserCheck, ZoomIn } from 'lucide-react'

// Every card here is a shipped, demoable feature — no roadmap items.
const FEATURES = [
  {
    icon: Gauge,
    title: 'Never a confident wrong answer',
    line: 'A confidence gate decides: advise, ask one field question, or send to an expert. Uncertainty is shown, not hidden.',
  },
  {
    icon: CloudRain,
    title: 'Alerts before damage shows',
    line: 'Weather, crop stage, trap counts and confirmed nearby cases tell each farm where to look — with the exact check to do.',
  },
  {
    icon: ZoomIn,
    title: 'Explainable diagnosis',
    line: 'Trained on ICAR and field photos of rice, maize and cotton. Grad-CAM shows the part of the leaf the model looked at.',
  },
  {
    icon: Ban,
    title: 'Chemical last, veto first',
    line: 'Advice runs field practice → natural control → chemical. The spray check stops the wrong bottle; it never calls one "safe".',
  },
  {
    icon: Languages,
    title: 'Marathi & Hindi, read aloud',
    line: 'Every advisory, alert and question in the farmer’s language, spoken with Sarvam AI voice. Speak a product name instead of typing it.',
  },
  {
    icon: Bug,
    title: 'Traps and field sensors',
    line: 'Pheromone-trap counts checked against ICAR action levels; a farm’s own sensor overrides the district forecast.',
  },
  {
    icon: UserCheck,
    title: 'Expert validation in 3 minutes',
    line: 'Escalated cases arrive pre-packed for the KVK expert. Each verdict updates the farmer, nearby farms and the model’s field record.',
  },
  {
    icon: Map,
    title: 'Officials’ surveillance',
    line: 'Hotspot map, risk outlook, field accuracy, IMD rainfall against normal and the state pesticide-use baseline.',
  },
]

export default function Features() {
  return (
    <section id="features" className="w-full bg-cream text-soil-dark">
      <div className="max-w-6xl mx-auto px-6 md:px-12 py-16 md:py-24">
        <h2 className="font-instrument-serif text-3xl sm:text-4xl md:text-5xl leading-tight max-w-3xl">
          Built for how farmers actually work — and honest when it isn’t sure.
        </h2>
        <div className="mt-10 md:mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map(({ icon: Icon, title, line }) => (
            <div key={title} className="rounded-2xl border border-soil-dark/10 bg-white/70 p-6">
              <Icon className="w-6 h-6 text-leaf" />
              <h3 className="mt-4 text-base font-medium">{title}</h3>
              <p className="mt-2 text-sm font-light leading-relaxed text-soil-dark/70">{line}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
