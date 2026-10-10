import { INPUT_MAX_LENGTH } from '../../api/contracts'

type ChatInputProps = {
  value: string
  disabled: boolean
  onChange: (value: string) => void
  onSend: () => void
}

export function ChatInput({ value, disabled, onChange, onSend }: ChatInputProps) {
  return (
    <div>
      <label htmlFor="agent-question" className="text-sm font-medium text-slate-700">
        办理问题
      </label>
      <textarea
        id="agent-question"
        aria-label="办理问题"
        className="mt-2 min-h-28 w-full resize-y rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm leading-6 text-slate-900"
        maxLength={INPUT_MAX_LENGTH}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault()
            if (!disabled) onSend()
          }
        }}
      />
      <p className="mt-1 text-right text-xs text-slate-500">
        {value.length}/{INPUT_MAX_LENGTH}
      </p>
    </div>
  )
}
