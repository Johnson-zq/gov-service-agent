import { Plus, RotateCcw, Send } from 'lucide-react'
import type { UseAgentChatResult } from '../../hooks/useAgentChat'
import { presentation } from '../../content/presentation'
import { ChatInput } from './ChatInput'
import { MessageBubble } from './MessageBubble'

type ChatPanelProps = {
  chat: UseAgentChatResult
  draft: string
  onDraftChange: (value: string) => void
  onSend: () => void
  onExample: () => void
}

function formatLatency(ms: number): string {
  if (ms < 1000) return `本次请求耗时 ${ms} ms`
  return `本次请求耗时 ${(ms / 1000).toFixed(1)} s`
}

export function ChatPanel({ chat, draft, onDraftChange, onSend, onExample }: ChatPanelProps) {
  const lastAssistant = [...chat.messages].reverse().find((message) => message.role === 'assistant')
  const sendDisabled = chat.isSending || chat.sessionInvalid || draft.trim().length === 0
  const showRetry = Boolean(chat.transportError?.retryable && chat.pendingRequest && !chat.sessionInvalid)

  return (
    <div className="flex min-w-0 flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-lg font-medium text-gov-900">实时办理对话</h3>
        {chat.serverSessionId ? (
          <p className="text-xs text-slate-500">会话 {chat.serverSessionId.slice(0, 8)}</p>
        ) : (
          <p className="text-xs text-slate-500">尚未建立会话</p>
        )}
      </div>

      <div className="flex min-h-64 flex-col gap-3" aria-live="polite">
        {chat.messages.length === 0 ? (
          <p className="text-sm text-slate-600">{presentation.demo.empty}</p>
        ) : (
          chat.messages.map((message) => <MessageBubble key={message.local_id} message={message} />)
        )}
        {chat.isSending ? <p className="text-sm text-gov-700">{presentation.loading}</p> : null}
      </div>

      {lastAssistant?.status === 'AWAITING_USER_INPUT' ? (
        <p className="text-sm text-gov-800">{presentation.awaitingHint}</p>
      ) : null}
      {lastAssistant?.status === 'COMPLETED' ? (
        <p className="text-sm text-gov-800">{presentation.completedHint}</p>
      ) : null}
      {typeof lastAssistant?.latency_ms === 'number' ? (
        <p className="text-xs text-slate-500">{formatLatency(lastAssistant.latency_ms)}</p>
      ) : null}
      {chat.unconfirmed ? <p className="text-sm text-amber-900">{presentation.unconfirmed}</p> : null}
      {chat.sessionInvalid ? <p className="text-sm text-amber-950">{presentation.sessionInvalid}</p> : null}
      {chat.transportError ? (
        <p role="alert" className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950">
          {chat.transportError.message}
        </p>
      ) : null}

      <ChatInput value={draft} disabled={chat.isSending || chat.sessionInvalid} onChange={onDraftChange} onSend={onSend} />

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-lg bg-gov-700 px-4 py-2 text-sm text-white disabled:cursor-not-allowed disabled:bg-slate-300"
          disabled={sendDisabled}
          onClick={onSend}
        >
          <Send aria-hidden="true" size={16} />
          发送
        </button>
        <button
          type="button"
          className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
          disabled={chat.isSending}
          onClick={onExample}
        >
          填入示例问题
        </button>
        {showRetry ? (
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-lg border border-gov-700 px-4 py-2 text-sm text-gov-800 disabled:cursor-not-allowed"
            disabled={chat.isSending}
            onClick={() => {
              void chat.retry()
            }}
          >
            <RotateCcw aria-hidden="true" size={16} />
            重试
          </button>
        ) : null}
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
          disabled={chat.isSending}
          onClick={chat.requestNewSession}
        >
          <Plus aria-hidden="true" size={16} />
          新建会话
        </button>
      </div>
    </div>
  )
}
