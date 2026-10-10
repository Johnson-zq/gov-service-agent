import type { HealthState } from '../../api/contracts'

const LABEL: Record<HealthState, string> = {
  UNKNOWN: '检查中',
  CHECKING: '检查中',
  AVAILABLE: 'Agent 服务正常',
  UNAVAILABLE: 'Agent 服务当前不可用',
}

export function ServiceStatus({ health }: { health: HealthState }) {
  const tone =
    health === 'AVAILABLE'
      ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
      : health === 'UNAVAILABLE'
        ? 'border-amber-200 bg-amber-50 text-amber-950'
        : 'border-slate-200 bg-white text-slate-700'

  return (
    <p
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm ${tone}`}
      role="status"
      aria-live="polite"
    >
      <span aria-hidden="true" className="text-xs">
        {health === 'AVAILABLE' ? '●' : health === 'UNAVAILABLE' ? '▲' : '○'}
      </span>
      {LABEL[health]}
    </p>
  )
}
