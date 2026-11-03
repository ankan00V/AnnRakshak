import { FarmerProvider } from './farmer/FarmerContext'
import Hero from './Hero'
import Problem from './sections/Problem'
import InTheField from './sections/InTheField'
import HowItWorks from './sections/HowItWorks'
import Features from './sections/Features'
import Impact from './sections/Impact'
import FinalCta from './sections/FinalCta'

/** The language chosen here is the one sign-up starts in (both read LANG_KEY). */
export default function Landing() {
  return (
    <FarmerProvider>
      <Hero />
      <Problem />
      <InTheField />
      <HowItWorks />
      <Features />
      <Impact />
      <FinalCta />
    </FarmerProvider>
  )
}
