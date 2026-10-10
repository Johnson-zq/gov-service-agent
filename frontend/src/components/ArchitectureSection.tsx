import { motion, useReducedMotion } from 'framer-motion'
import { Network } from 'lucide-react'
import type { ReactNode } from 'react'
import { presentation } from '../content/presentation'

function Reveal({ children }: { children: ReactNode }) {
  const reduce = useReducedMotion()
  return (
    <motion.section
      id="architecture"
      className="mx-auto max-w-7xl px-4 py-12"
      initial={reduce ? false : { opacity: 0, y: 12 }}
      whileInView={reduce ? undefined : { opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.15 }}
      transition={{ duration: 0.35 }}
    >
      {children}
    </motion.section>
  )
}

export function ArchitectureSection() {
  return (
    <Reveal>
      <div className="flex items-center gap-2">
        <Network aria-hidden="true" className="text-gov-700" />
        <h2 className="text-2xl font-semibold text-gov-900">{presentation.architecture.title}</h2>
      </div>
      <p className="mt-2 text-sm text-slate-600">{presentation.architecture.disclaimer}</p>
      <ol className="mt-6 grid gap-3">
        {presentation.architecture.steps.map((step, index) => (
          <li key={step.name}>
            {index > 0 ? <hr className="flow-connector mb-3" /> : null}
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
              <p className="font-medium text-gov-900">
                {index + 1}. {step.name}
              </p>
              <p className="mt-1 text-sm text-slate-600">{step.note}</p>
            </div>
          </li>
        ))}
      </ol>
    </Reveal>
  )
}
