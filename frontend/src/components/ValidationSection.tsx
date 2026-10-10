import { motion, useReducedMotion } from 'framer-motion'
import { ListChecks } from 'lucide-react'
import type { ReactNode } from 'react'
import { presentation } from '../content/presentation'

function Reveal({ children }: { children: ReactNode }) {
  const reduce = useReducedMotion()
  return (
    <motion.section
      id="validation"
      className="mx-auto max-w-7xl px-4 py-12"
      initial={reduce ? false : { opacity: 0, y: 12 }}
      whileInView={reduce ? undefined : { opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.3 }}
      transition={{ duration: 0.35 }}
    >
      {children}
    </motion.section>
  )
}

export function ValidationSection() {
  return (
    <Reveal>
      <div className="flex items-center gap-2">
        <ListChecks aria-hidden="true" className="text-gov-700" />
        <h2 className="text-2xl font-semibold text-gov-900">{presentation.validation.title}</h2>
      </div>
      <div className="mt-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <p className="text-lg font-medium text-gov-900">{presentation.validation.headline}</p>
        <p className="mt-3 text-sm text-slate-700">{presentation.validation.review}</p>
        <p className="mt-3 text-sm text-slate-700">{presentation.validation.f13}</p>
        <p className="mt-4 text-xs text-slate-500">{presentation.validation.footnote}</p>
      </div>
    </Reveal>
  )
}
