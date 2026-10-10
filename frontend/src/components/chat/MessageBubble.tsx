import type { ChatMessage } from '../../api/contracts'

export function MessageBubble({ message }: { message: ChatMessage }) {
  const mine = message.role === 'user'
  return (
    <article
      className={`max-w-[85%] rounded-xl px-4 py-3 text-sm leading-6 shadow-sm ${
        mine ? 'ml-auto bg-gov-700 text-white' : 'mr-auto border border-slate-200 bg-white text-slate-800'
      }`}
    >
      <p className="agent-text">{message.text}</p>
    </article>
  )
}
