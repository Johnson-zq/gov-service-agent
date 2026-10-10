import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { AgentClient } from '../api/agentClient'
import { HEALTH_POLL_INTERVAL_MS, useAgentHealth } from './useAgentHealth'

function clientWith(checkHealth: AgentClient['checkHealth']): AgentClient {
  return { checkHealth, sendTurn: vi.fn() }
}

describe('useAgentHealth', () => {
  it('checks immediately and becomes AVAILABLE', async () => {
    let resolveCheck: (value: 'AVAILABLE' | 'UNAVAILABLE') => void = () => {}
    const checkHealth = vi.fn(
      () =>
        new Promise<'AVAILABLE' | 'UNAVAILABLE'>((resolve) => {
          resolveCheck = resolve
        }),
    )
    const client = clientWith(checkHealth)
    const { result } = renderHook(() => useAgentHealth(client))
    await waitFor(() => expect(result.current).toBe('CHECKING'))
    await act(async () => {
      resolveCheck('AVAILABLE')
    })
    await waitFor(() => expect(result.current).toBe('AVAILABLE'))
    expect(checkHealth).toHaveBeenCalledTimes(1)
  })

  it('becomes UNAVAILABLE when the check fails', async () => {
    const checkHealth = vi.fn().mockResolvedValue('UNAVAILABLE')
    const client = clientWith(checkHealth)
    const { result } = renderHook(() => useAgentHealth(client))
    await waitFor(() => expect(result.current).toBe('UNAVAILABLE'))
  })

  it('polls again after 30 seconds and stops after cleanup', async () => {
    vi.useFakeTimers()
    const checkHealth = vi.fn().mockResolvedValue('AVAILABLE')
    const client = clientWith(checkHealth)
    try {
      const { result, unmount } = renderHook(() => useAgentHealth(client))

      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(checkHealth).toHaveBeenCalledTimes(1)
      expect(result.current).toBe('AVAILABLE')

      await act(async () => {
        await vi.advanceTimersByTimeAsync(HEALTH_POLL_INTERVAL_MS)
      })
      expect(checkHealth).toHaveBeenCalledTimes(2)
      expect(result.current).toBe('AVAILABLE')

      unmount()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(HEALTH_POLL_INTERVAL_MS)
      })
      expect(checkHealth).toHaveBeenCalledTimes(2)
    } finally {
      vi.useRealTimers()
    }
  })
})
