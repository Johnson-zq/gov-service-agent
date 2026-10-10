import { useEffect, useState } from 'react'
import { agentClient, type AgentClient } from '../api/agentClient'
import type { HealthState } from '../api/contracts'

export const HEALTH_POLL_INTERVAL_MS = 30000

export function useAgentHealth(client: AgentClient = agentClient): HealthState {
  const [health, setHealth] = useState<HealthState>('UNKNOWN')

  useEffect(() => {
    let cancelled = false

    const run = () => {
      setHealth('CHECKING')
      void client.checkHealth().then((next) => {
        if (!cancelled) setHealth(next)
      })
    }

    run()
    const timer = window.setInterval(run, HEALTH_POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [client])

  return health
}
