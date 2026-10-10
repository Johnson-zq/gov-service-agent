import { useState } from 'react'
import type { HealthState } from '../api/contracts'
import { presentation } from '../content/presentation'
import { useAgentChat } from '../hooks/useAgentChat'
import { ChatPanel } from './chat/ChatPanel'
import { ServiceStatus } from './chat/ServiceStatus'

export function AgentDemoSection({ health }: { health: HealthState }) {
  const chat = useAgentChat()
  const [draft, setDraft] = useState('')

  return (
    <section id="demo" className="mx-auto max-w-7xl px-4 py-12">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold text-gov-900">{presentation.demo.title}</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">{presentation.demo.lead}</p>
        </div>
        <ServiceStatus health={health} />
      </div>
      <div className="mt-6 grid min-w-0 grid-cols-1 gap-4 xl:grid-cols-2">
        <ChatPanel
          chat={chat}
          draft={draft}
          onDraftChange={setDraft}
          onExample={() => setDraft(presentation.exampleQuestion)}
          onSend={() => {
            void chat.sendMessage(draft).then((accepted) => {
              if (accepted) setDraft('')
            })
          }}
        />
        <aside className="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="text-lg font-medium text-gov-900">{presentation.demo.capabilityTitle}</h3>
          <ul className="mt-4 space-y-3 text-sm leading-6 text-slate-700">
            {presentation.demo.capabilities.map((item) => (
              <li key={item} className="rounded-lg bg-gov-50 px-3 py-2">
                {item}
              </li>
            ))}
          </ul>
        </aside>
      </div>
    </section>
  )
}
