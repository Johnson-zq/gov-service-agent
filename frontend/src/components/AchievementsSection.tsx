import { motion, useReducedMotion } from 'framer-motion'
import { BadgeCheck } from 'lucide-react'
import type { ReactNode } from 'react'
import { presentation } from '../content/presentation'

function Reveal({ children }: { children: ReactNode }) {
  const reduce = useReducedMotion()
  return (
    <motion.section
      id="achievements"
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

export function AchievementsSection() {
  return (
    <Reveal>
      <h2 className="text-2xl font-semibold text-gov-900">{presentation.achievements.title}</h2>
      <p className="mt-2 text-sm text-slate-600">{presentation.achievements.note}</p>
      <ul className="mt-6 grid gap-4 md:grid-cols-2">
        {presentation.achievements.cards.map((card) => (
          <li key={card.title} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center gap-2 text-gov-800">
              <BadgeCheck aria-hidden="true" size={18} />
              <h3 className="font-medium">{card.title}</h3>
            </div>
            <p className="mt-3 text-sm leading-6 text-slate-700">{card.body}</p>
          </li>
        ))}
      </ul>
    </Reveal>
  )
}
