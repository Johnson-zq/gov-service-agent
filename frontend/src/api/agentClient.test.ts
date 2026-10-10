import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  HEALTH_TIMEOUT_MS,
  TURN_TIMEOUT_MS,
  checkHealth,
  sendTurn,
  type SendTurnInput,
} from './agentClient'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function successBody(overrides: Record<string, unknown> = {}) {
  return {
    session_id: 'server-session-1',
    request_id: 'req-1',
    status: 'COMPLETED',
    response_text: '公开答复',
    requires_user_input: false,
    ...overrides,
  }
}

const firstTurn: SendTurnInput = {
  requestId: 'req-1',
  inputText: '我想办理',
  sessionId: null,
}

afterEach(() => {
  vi.useRealTimers()
})

describe('checkHealth', () => {
  it('returns AVAILABLE only for an ok payload', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(200, { status: 'ok' }))
    await expect(checkHealth(fetchImpl)).resolves.toBe('AVAILABLE')
    expect(fetchImpl).toHaveBeenCalledWith('/health', expect.objectContaining({ method: 'GET' }))
  })

  it('returns UNAVAILABLE for HTTP failure, bad payload, and network failure', async () => {
    await expect(checkHealth(vi.fn().mockResolvedValue(jsonResponse(500, { status: 'ok' })))).resolves.toBe(
      'UNAVAILABLE',
    )
    await expect(checkHealth(vi.fn().mockResolvedValue(jsonResponse(200, { status: 'down' })))).resolves.toBe(
      'UNAVAILABLE',
    )
    await expect(checkHealth(vi.fn().mockRejectedValue(new TypeError('offline')))).resolves.toBe('UNAVAILABLE')
  })

  it('treats an aborted health check as unavailable', async () => {
    vi.useFakeTimers()
    const fetchImpl = vi.fn((_url: string, init?: RequestInit) => {
      return new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => {
          reject(new DOMException('Aborted', 'AbortError'))
        })
      })
    })
    const pending = checkHealth(fetchImpl)
    await vi.advanceTimersByTimeAsync(HEALTH_TIMEOUT_MS)
    await expect(pending).resolves.toBe('UNAVAILABLE')
  })
})

describe('sendTurn', () => {
  it('omits session_id on the first turn and keeps request_id unchanged', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(200, successBody()))
    const result = await sendTurn(firstTurn, fetchImpl)
    const [, init] = fetchImpl.mock.calls[0] as [string, RequestInit]
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({
      request_id: 'req-1',
      input_text: '我想办理',
    })
    expect(result.ok).toBe(true)
  })

  it('includes session_id only when one was supplied', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      jsonResponse(200, successBody({ session_id: 'session-keep' })),
    )
    await sendTurn({ ...firstTurn, sessionId: 'session-keep' }, fetchImpl)
    const [, init] = fetchImpl.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(String(init.body))).toEqual({
      request_id: 'req-1',
      input_text: '我想办理',
      session_id: 'session-keep',
    })
  })

  it('accepts COMPLETED and AWAITING_USER_INPUT when the invariant holds', async () => {
    const completed = await sendTurn(
      firstTurn,
      vi.fn().mockResolvedValue(jsonResponse(200, successBody())),
    )
    const awaiting = await sendTurn(
      firstTurn,
      vi.fn().mockResolvedValue(
        jsonResponse(
          200,
          successBody({ status: 'AWAITING_USER_INPUT', requires_user_input: true, response_text: '请补充' }),
        ),
      ),
    )
    expect(completed.ok && completed.response.response_text).toBe('公开答复')
    expect(awaiting.ok && awaiting.response.requires_user_input).toBe(true)
  })

  it('rejects status and requires_user_input mismatches', async () => {
    const mismatched = await sendTurn(
      firstTurn,
      vi.fn().mockResolvedValue(jsonResponse(200, successBody({ requires_user_input: true }))),
    )
    const awaitingMismatch = await sendTurn(
      firstTurn,
      vi.fn().mockResolvedValue(
        jsonResponse(200, successBody({ status: 'AWAITING_USER_INPUT', requires_user_input: false })),
      ),
    )
    expect(mismatched).toMatchObject({ ok: false, error: { category: 'INVALID_RESPONSE' } })
    expect(awaitingMismatch).toMatchObject({ ok: false, error: { category: 'INVALID_RESPONSE' } })
  })

  it('rejects a different request id, a switched session id, and a malformed success body', async () => {
    const requestMismatch = await sendTurn(
      firstTurn,
      vi.fn().mockResolvedValue(jsonResponse(200, successBody({ request_id: 'other' }))),
    )
    const sessionMismatch = await sendTurn(
      { ...firstTurn, sessionId: 'session-keep' },
      vi.fn().mockResolvedValue(jsonResponse(200, successBody({ session_id: 'session-other' }))),
    )
    const malformed = await sendTurn(firstTurn, vi.fn().mockResolvedValue(jsonResponse(200, { status: 'COMPLETED' })))
    expect(requestMismatch).toMatchObject({ ok: false, error: { category: 'INVALID_RESPONSE' } })
    expect(sessionMismatch).toMatchObject({ ok: false, error: { category: 'INVALID_RESPONSE' } })
    expect(malformed).toMatchObject({ ok: false, error: { category: 'INVALID_RESPONSE' } })
  })

  it.each([
    [422, {}, 'INVALID_REQUEST'],
    [404, {}, 'SESSION_NOT_FOUND'],
    [410, {}, 'SESSION_EXPIRED'],
    [409, { error: { code: 'REQUEST_ID_REUSE_CONFLICT', message: 'raw' } }, 'REQUEST_ID_REUSE_CONFLICT'],
    [409, { error: { code: 'REQUEST_IN_PROGRESS', message: 'raw' } }, 'REQUEST_IN_PROGRESS'],
    [500, { error: { code: 'INTERNAL', message: 'stack' } }, 'AGENT_FAILURE'],
    [503, { raw: true }, 'PERSISTENCE_UNAVAILABLE'],
  ] as const)('maps HTTP %s to %s without exposing the raw body', async (status, body, category) => {
    const result = await sendTurn(firstTurn, vi.fn().mockResolvedValue(jsonResponse(status, body)))
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.error.category).toBe(category)
      expect(result.error.message).not.toContain('raw')
      expect(result.error.message).not.toContain('stack')
    }
  })

  it('returns NETWORK_ERROR when fetch rejects', async () => {
    const result = await sendTurn(firstTurn, vi.fn().mockRejectedValue(new TypeError('offline')))
    expect(result).toMatchObject({ ok: false, error: { category: 'NETWORK_ERROR', retryable: true } })
  })

  it('returns TIMEOUT when the turn is aborted at 90 seconds', async () => {
    vi.useFakeTimers()
    const fetchImpl = vi.fn((_url: string, init?: RequestInit) => {
      return new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => {
          reject(new DOMException('Aborted', 'AbortError'))
        })
      })
    })
    const pending = sendTurn(firstTurn, fetchImpl)
    await vi.advanceTimersByTimeAsync(TURN_TIMEOUT_MS)
    await expect(pending).resolves.toMatchObject({
      ok: false,
      error: { category: 'TIMEOUT', retryable: true },
    })
  })
})
