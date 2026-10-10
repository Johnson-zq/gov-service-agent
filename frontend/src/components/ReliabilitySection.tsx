import { motion, useReducedMotion } from 'framer-motion'
import { ShieldCheck } from 'lucide-react'
import type { ReactNode } from 'react'
import { presentation } from '../content/presentation'

function Reveal({ children }: { children: ReactNode }) {
  const reduce = useReducedMotion()
  return (
    <motion.section
      id="reliability"
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

export function ReliabilitySection() {
  return (
    <Reveal>
      <div className="flex items-center gap-2">
        <ShieldCheck aria-hidden="true" className="text-gov-700" />
        <h2 className="text-2xl font-semibold text-gov-900">{presentation.reliability.title}</h2>
      </div>
      <ul className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {presentation.reliability.cards.map((card) => (
          <li key={card.title} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="font-medium text-gov-900">{card.title}</h3>
            <p className="mt-2 text-sm leading-6 text-slate-700">{card.body}</p>
          </li>
        ))}
      </ul>
    </Reveal>
  )
}
