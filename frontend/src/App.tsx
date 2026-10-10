import { AchievementsSection } from './components/AchievementsSection'
import { AgentDemoSection } from './components/AgentDemoSection'
import { ArchitectureSection } from './components/ArchitectureSection'
import { HeroSection } from './components/HeroSection'
import { Navigation } from './components/Navigation'
import { NextStepsSection } from './components/NextStepsSection'
import { ReliabilitySection } from './components/ReliabilitySection'
import { RoadmapSection } from './components/RoadmapSection'
import { ValidationSection } from './components/ValidationSection'
import { useAgentHealth } from './hooks/useAgentHealth'

export function App() {
  const health = useAgentHealth()

  return (
    <div className="min-h-screen bg-gov-50 text-slate-900">
      <Navigation />
      <main>
        <HeroSection health={health} />
        <AchievementsSection />
        <ArchitectureSection />
        <AgentDemoSection health={health} />
        <RoadmapSection />
        <ReliabilitySection />
        <ValidationSection />
        <NextStepsSection />
      </main>
    </div>
  )
}
