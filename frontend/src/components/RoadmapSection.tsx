import { motion, useReducedMotion } from 'framer-motion'
import { Route } from 'lucide-react'
import type { ReactNode } from 'react'
import { presentation } from '../content/presentation'

function Reveal({ children }: { children: ReactNode }) {
  const reduce = useReducedMotion()
  return (
    <motion.section
      id="roadmap"
      className="mx-auto max-w-7xl px-4 py-12"
      initial={reduce ? false : { opacity: 0, y: 12 }}
      whileInView={reduce ? undefined : { opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.2 }}
      transition={{ duration: 0.35 }}
    >
      {children}
    </motion.section>
  )
}

export function RoadmapSection() {
  return (
    <Reveal>
      <div className="flex items-center gap-2">
        <Route aria-hidden="true" className="text-gov-700" />
        <h2 className="text-2xl font-semibold text-gov-900">{presentation.roadmap.title}</h2>
      </div>
      <ol className="mt-6 grid gap-3 md:grid-cols-2">
        {presentation.roadmap.steps.map((step, index) => (
          <li key={step} className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm shadow-sm">
            <span className="mr-2 font-medium text-gov-700">{index + 1}</span>
            {step}
          </li>
        ))}
      </ol>
    </Reveal>
  )
}
