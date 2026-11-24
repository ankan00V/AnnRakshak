import { FarmerProvider } from './farmer/FarmerContext'
import Hero from './Hero'
import HelpsYou from './sections/HelpsYou'
import InTheField from './sections/InTheField'
import HowItWorks from './sections/HowItWorks'
import Impact from './sections/Impact'
import District from './sections/District'
import FinalCta from './sections/FinalCta'

/** The language chosen here is the one sign-up starts in (both read LANG_KEY). */
export default function Landing() {
  return (
    <FarmerProvider>
      {/* Cream behind every section, so where two cream sections meet on a
          fraction of a pixel no hairline of the bare page shows through. */}
      <div className="bg-[#f6f1e6]">
        <Hero />
        <HelpsYou />
        <InTheField />
        <HowItWorks />
        <Impact />
        <District />
        <FinalCta />
      </div>
    </FarmerProvider>
  )
}
