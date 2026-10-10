import { motion, useReducedMotion } from 'framer-motion'
import { Landmark } from 'lucide-react'
import type { ReactNode } from 'react'
import type { HealthState } from '../api/contracts'
import { presentation } from '../content/presentation'
import { ServiceStatus } from './chat/ServiceStatus'

function Reveal({ children }: { children: ReactNode }) {
  const reduce = useReducedMotion()
  return (
    <motion.section
      id="overview"
      className="mx-auto max-w-7xl px-4 py-16"
      initial={reduce ? false : { opacity: 0, y: 12 }}
      whileInView={reduce ? undefined : { opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.3 }}
      transition={{ duration: 0.35 }}
    >
      {children}
    </motion.section>
  )
}

export function HeroSection({ health }: { health: HealthState }) {
  return (
    <Reveal>
      <p className="text-sm font-medium tracking-wide text-gov-700">{presentation.hero.eyebrow}</p>
      <div className="mt-4 flex items-start gap-3">
        <Landmark aria-hidden="true" className="mt-1 text-gov-700" />
        <h1 className="text-3xl font-semibold text-gov-900 md:text-4xl">{presentation.hero.title}</h1>
      </div>
      <p className="mt-4 max-w-3xl text-base leading-7 text-slate-700">{presentation.hero.summary}</p>
      <ul className="mt-6 flex flex-wrap gap-2">
        {presentation.hero.points.map((point) => (
          <li key={point} className="rounded-full bg-white px-3 py-1 text-sm text-slate-700 shadow-sm">
            {point}
          </li>
        ))}
      </ul>
      <div className="mt-6">
        <ServiceStatus health={health} />
      </div>
    </Reveal>
  )
}
