import { motion, useReducedMotion } from 'framer-motion'
import { Building2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { presentation } from '../content/presentation'

function Reveal({ children }: { children: ReactNode }) {
  const reduce = useReducedMotion()
  return (
    <motion.section
      id="next"
      className="mx-auto max-w-7xl px-4 py-12 pb-20"
      initial={reduce ? false : { opacity: 0, y: 12 }}
      whileInView={reduce ? undefined : { opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.2 }}
      transition={{ duration: 0.35 }}
    >
      {children}
    </motion.section>
  )
}

export function NextStepsSection() {
  return (
    <Reveal>
      <div className="flex items-center gap-2">
        <Building2 aria-hidden="true" className="text-gov-700" />
        <h2 className="text-2xl font-semibold text-gov-900">{presentation.next.title}</h2>
      </div>
      <p className="mt-2 text-sm text-slate-600">{presentation.next.caution}</p>
      <ul className="mt-6 grid gap-3 md:grid-cols-2">
        {presentation.next.items.map((item) => (
          <li key={item} className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm shadow-sm">
            {item}
          </li>
        ))}
      </ul>
    </Reveal>
  )
}
