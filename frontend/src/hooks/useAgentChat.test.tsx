import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { AgentClient, SendTurnInput, SendTurnResult } from '../api/agentClient'
import type { FrontendErrorCategory } from '../api/contracts'
import { INPUT_MAX_LENGTH } from '../api/contracts'
import { loadDemoPersistence, saveDemoPersistence } from '../storage/sessionStorage'
import { presentation } from '../content/presentation'
import { useAgentChat } from './useAgentChat'

function ok(input: SendTurnInput, text = '原样答复'): SendTurnResult {
  return {
    ok: true,
    latencyMs: 42,
    response: {
      session_id: input.sessionId ?? 'server-session-1',
      request_id: input.requestId,
      status: 'COMPLETED',
      response_text: text,
      requires_user_input: false,
    },
  }
}

function fail(category: FrontendErrorCategory, retryable: boolean): SendTurnResult {
  return { ok: false, error: { category, message: '安全提示', retryable } }
}

function clientOf(sendTurn: AgentClient['sendTurn']): AgentClient {
  return { checkHealth: vi.fn(), sendTurn }
}

describe('useAgentChat', () => {
  it('creates a new request id and omits session id on the first turn', async () => {
    const sendTurn = vi.fn(async (input: SendTurnInput) => ok(input))
    const { result } = renderHook(() => useAgentChat(clientOf(sendTurn)))
    await act(async () => {
      await result.current.sendMessage('  你好  ')
    })
    const first = sendTurn.mock.calls[0][0]
    expect(first.sessionId).toBeNull()
    expect(first.inputText).toBe('你好')
    expect(first.requestId).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    )
    expect(result.current.serverSessionId).toBe('server-session-1')
    expect(result.current.messages.map((message) => message.text)).toEqual(['你好', '原样答复'])
    expect(result.current.messages[1]?.latency_ms).toBe(42)
  })

  it('reuses the server session id and issues a new request id on the next turn', async () => {
    const sendTurn = vi.fn(async (input: SendTurnInput) => ok(input, input.inputText))
    const { result } = renderHook(() => useAgentChat(clientOf(sendTurn)))
    await act(async () => {
      await result.current.sendMessage('第一句')
    })
    await act(async () => {
      await result.current.sendMessage('第二句')
    })
    expect(sendTurn.mock.calls[1][0].sessionId).toBe('server-session-1')
    expect(sendTurn.mock.calls[0][0].requestId).not.toBe(sendTurn.mock.calls[1][0].requestId)
    expect(result.current.messages.filter((message) => message.role === 'assistant').map((message) => message.text)).toEqual([
      '第一句',
      '第二句',
    ])
  })

  it('retries the same first-turn identity without a second user message', async () => {
    const sendTurn = vi
      .fn<AgentClient['sendTurn']>()
      .mockResolvedValueOnce(fail('TIMEOUT', true))
      .mockImplementation(async (input) => ok(input, '重试后的答复'))
    const { result } = renderHook(() => useAgentChat(clientOf(sendTurn)))
    await act(async () => {
      await result.current.sendMessage('同一句')
    })
    await act(async () => {
      await result.current.retry()
    })
    expect(sendTurn.mock.calls[1][0]).toEqual(sendTurn.mock.calls[0][0])
    expect(sendTurn.mock.calls[1][0].sessionId).toBeNull()
    expect(result.current.messages.filter((message) => message.role === 'user')).toHaveLength(1)
    expect(result.current.messages.at(-1)?.text).toBe('重试后的答复')
  })

  it('keeps the original session id captured when the turn was dispatched', async () => {
    saveDemoPersistence({
      sessionId: 'already-known',
      messages: [],
      pendingRequest: {
        requestId: 'pending-req',
        inputText: '未完成',
        sessionIdAtDispatch: null,
        startedAt: '2026-01-01T00:00:00.000Z',
      },
    })
    const sendTurn = vi.fn(async (input: SendTurnInput) => ok(input))
    const { result } = renderHook(() => useAgentChat(clientOf(sendTurn)))
    expect(sendTurn).not.toHaveBeenCalled()
    await act(async () => {
      await result.current.retry()
    })
    expect(sendTurn).toHaveBeenCalledWith({
      requestId: 'pending-req',
      inputText: '未完成',
      sessionId: null,
    })
  })

  it('replaces a failed turn with a new request id when the user edits the input', async () => {
    const sendTurn = vi
      .fn<AgentClient['sendTurn']>()
      .mockResolvedValueOnce(fail('NETWORK_ERROR', true))
      .mockImplementation(async (input) => ok(input))
    const { result } = renderHook(() => useAgentChat(clientOf(sendTurn)))
    await act(async () => {
      await result.current.sendMessage('旧内容')
    })
    await act(async () => {
      await result.current.sendMessage('新内容')
    })
    expect(sendTurn.mock.calls[0][0].inputText).toBe('旧内容')
    expect(sendTurn.mock.calls[1][0].inputText).toBe('新内容')
    expect(sendTurn.mock.calls[0][0].requestId).not.toBe(sendTurn.mock.calls[1][0].requestId)
  })

  it('clears chat state on a confirmed new session and does not call the backend', async () => {
    const sendTurn = vi.fn(async (input: SendTurnInput) => ok(input))
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const { result } = renderHook(() => useAgentChat(clientOf(sendTurn)))
    await act(async () => {
      await result.current.sendMessage('会留下')
    })
    act(() => {
      result.current.requestNewSession()
    })
    expect(confirm).toHaveBeenCalledWith(presentation.newSessionConfirm)
    expect(sendTurn).toHaveBeenCalledTimes(1)
    expect(result.current.messages).toEqual([])
    expect(result.current.serverSessionId).toBeNull()
    expect(result.current.pendingRequest).toBeNull()
    expect(loadDemoPersistence()).toEqual({
      sessionId: null,
      messages: [],
      pendingRequest: null,
    })
    confirm.mockRestore()
  })

  it('does not ask for confirmation when the chat is empty', () => {
    const confirm = vi.spyOn(window, 'confirm')
    const { result } = renderHook(() => useAgentChat(clientOf(vi.fn())))
    act(() => {
      result.current.requestNewSession()
    })
    expect(confirm).not.toHaveBeenCalled()
    confirm.mockRestore()
  })

  it('ignores a second send while the first request is in flight', async () => {
    let release: (value: SendTurnResult) => void = () => {}
    const sendTurn = vi.fn(
      (input: SendTurnInput) =>
        new Promise<SendTurnResult>((resolve) => {
          release = () => resolve(ok(input))
        }),
    )
    const { result } = renderHook(() => useAgentChat(clientOf(sendTurn)))
    act(() => {
      void result.current.sendMessage('第一条')
    })
    await waitFor(() => expect(result.current.isSending).toBe(true))
    await act(async () => {
      await result.current.sendMessage('第二条')
    })
    expect(sendTurn).toHaveBeenCalledTimes(1)
    await act(async () => {
      release()
    })
  })

  it('restores persisted chat and does not auto-send a pending request', () => {
    saveDemoPersistence({
      sessionId: 'saved-session',
      messages: [
        {
          local_id: 'local-1',
          role: 'user',
          text: '已保存',
          request_id: 'req-saved',
          created_at: '2026-01-01T00:00:00.000Z',
        },
      ],
      pendingRequest: {
        requestId: 'req-saved',
        inputText: '已保存',
        sessionIdAtDispatch: 'saved-session',
        startedAt: '2026-01-01T00:00:00.000Z',
      },
    })
    const sendTurn = vi.fn()
    const { result } = renderHook(() => useAgentChat(clientOf(sendTurn)))
    expect(sendTurn).not.toHaveBeenCalled()
    expect(result.current.unconfirmed).toBe(true)
    expect(result.current.serverSessionId).toBe('saved-session')
    expect(result.current.messages[0]?.text).toBe('已保存')
  })

  it.each(['SESSION_NOT_FOUND', 'SESSION_EXPIRED'] as const)(
    'marks the session invalid after %s and blocks another send',
    async (category) => {
      const sendTurn = vi.fn().mockResolvedValue(fail(category, false))
      const { result } = renderHook(() => useAgentChat(clientOf(sendTurn)))
      await act(async () => {
        await result.current.sendMessage('继续问')
      })
      expect(result.current.sessionInvalid).toBe(true)
      expect(result.current.messages).toHaveLength(1)
      await act(async () => {
        await result.current.sendMessage('再问一次')
      })
      expect(sendTurn).toHaveBeenCalledTimes(1)
    },
  )

  it('rejects empty and overlong input before creating a request', async () => {
    const sendTurn = vi.fn(async (input: SendTurnInput) => ok(input, '边界内答复'))
    const { result } = renderHook(() => useAgentChat(clientOf(sendTurn)))
    await act(async () => {
      await result.current.sendMessage('   ')
      await result.current.sendMessage('字'.repeat(INPUT_MAX_LENGTH + 1))
    })
    expect(sendTurn).not.toHaveBeenCalled()
    expect(result.current.messages).toEqual([])
    expect(result.current.pendingRequest).toBeNull()
    await act(async () => {
      await result.current.sendMessage('字'.repeat(INPUT_MAX_LENGTH))
    })
    expect(sendTurn).toHaveBeenCalledTimes(1)
    expect(sendTurn.mock.calls[0]?.[0].inputText).toHaveLength(INPUT_MAX_LENGTH)
  })
})
