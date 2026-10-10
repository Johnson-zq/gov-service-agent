import type {
  FrontendError,
  FrontendErrorCategory,
  HealthResponse,
  SessionTurnRequest,
  SessionTurnSuccess,
} from './contracts'

export const HEALTH_TIMEOUT_MS = 3000
export const TURN_TIMEOUT_MS = 90000

export type HealthCheckResult = 'AVAILABLE' | 'UNAVAILABLE'

export type SendTurnInput = {
  requestId: string
  inputText: string
  sessionId: string | null
}

export type SendTurnResult =
  | { ok: true; response: SessionTurnSuccess; latencyMs: number }
  | { ok: false; error: FrontendError }

const SAFE_MESSAGE: Record<FrontendErrorCategory, string> = {
  NETWORK_ERROR: '网络连接失败，请稍后重试。',
  TIMEOUT: '请求超时，请稍后重试。',
  INVALID_REQUEST: '请求内容未能通过校验，请修改后重新发送。',
  SESSION_NOT_FOUND: '当前会话不存在。请新建会话后继续。',
  SESSION_EXPIRED: '当前会话已失效。请新建会话后继续。',
  REQUEST_ID_REUSE_CONFLICT: '该请求与已记录的内容不一致，请重新输入后发送。',
  REQUEST_IN_PROGRESS: '相同请求仍在处理中，请稍后手动重试。',
  AGENT_FAILURE: '服务处理失败，请稍后重试。',
  PERSISTENCE_UNAVAILABLE: '会话存储暂不可用，请稍后重试。',
  INVALID_RESPONSE: '服务返回内容无法识别。',
  UNKNOWN_ERROR: '服务暂时无法完成请求。',
}

const RETRYABLE: ReadonlySet<FrontendErrorCategory> = new Set([
  'NETWORK_ERROR',
  'TIMEOUT',
  'AGENT_FAILURE',
  'PERSISTENCE_UNAVAILABLE',
  'REQUEST_IN_PROGRESS',
])

export function createFrontendError(
  category: FrontendErrorCategory,
  httpStatus?: number,
): FrontendError {
  return {
    category,
    message: SAFE_MESSAGE[category],
    retryable: RETRYABLE.has(category),
    ...(httpStatus === undefined ? {} : { httpStatus }),
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function isHealthOk(value: unknown): value is HealthResponse {
  return isRecord(value) && value.status === 'ok'
}

export function validateSuccessPayload(
  payload: unknown,
  expectedRequestId: string,
  expectedSessionId: string | null,
): SessionTurnSuccess | FrontendError {
  if (!isRecord(payload)) return createFrontendError('INVALID_RESPONSE')
  if (!isNonEmptyString(payload.session_id)) return createFrontendError('INVALID_RESPONSE')
  if (!isNonEmptyString(payload.request_id)) return createFrontendError('INVALID_RESPONSE')
  if (payload.status !== 'COMPLETED' && payload.status !== 'AWAITING_USER_INPUT') {
    return createFrontendError('INVALID_RESPONSE')
  }
  if (typeof payload.response_text !== 'string') return createFrontendError('INVALID_RESPONSE')
  if (typeof payload.requires_user_input !== 'boolean') {
    return createFrontendError('INVALID_RESPONSE')
  }
  if (payload.status === 'COMPLETED' && payload.requires_user_input !== false) {
    return createFrontendError('INVALID_RESPONSE')
  }
  if (payload.status === 'AWAITING_USER_INPUT' && payload.requires_user_input !== true) {
    return createFrontendError('INVALID_RESPONSE')
  }
  if (payload.request_id !== expectedRequestId) return createFrontendError('INVALID_RESPONSE')
  if (expectedSessionId !== null && payload.session_id !== expectedSessionId) {
    return createFrontendError('INVALID_RESPONSE')
  }
  return {
    session_id: payload.session_id,
    request_id: payload.request_id,
    status: payload.status,
    response_text: payload.response_text,
    requires_user_input: payload.requires_user_input,
  }
}

function readErrorCode(body: unknown): string | null {
  if (!isRecord(body) || !isRecord(body.error) || typeof body.error.code !== 'string') {
    return null
  }
  return body.error.code
}

export function mapHttpError(status: number, body: unknown): FrontendError {
  const code = readErrorCode(body)
  if (status === 422) return createFrontendError('INVALID_REQUEST', status)
  if (status === 404) return createFrontendError('SESSION_NOT_FOUND', status)
  if (status === 410) return createFrontendError('SESSION_EXPIRED', status)
  if (status === 409 && code === 'REQUEST_ID_REUSE_CONFLICT') {
    return createFrontendError('REQUEST_ID_REUSE_CONFLICT', status)
  }
  if (status === 409 && code === 'REQUEST_IN_PROGRESS') {
    return createFrontendError('REQUEST_IN_PROGRESS', status)
  }
  if (status === 500) return createFrontendError('AGENT_FAILURE', status)
  if (status === 503) return createFrontendError('PERSISTENCE_UNAVAILABLE', status)
  return createFrontendError('UNKNOWN_ERROR', status)
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    return null
  }
}

export async function checkHealth(
  fetchImpl: typeof fetch = fetch,
): Promise<HealthCheckResult> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS)
  try {
    const response = await fetchImpl('/health', {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    })
    if (!response.ok) return 'UNAVAILABLE'
    const body = await readJson(response)
    return isHealthOk(body) ? 'AVAILABLE' : 'UNAVAILABLE'
  } catch {
    return 'UNAVAILABLE'
  } finally {
    clearTimeout(timer)
  }
}

export async function sendTurn(
  input: SendTurnInput,
  fetchImpl: typeof fetch = fetch,
): Promise<SendTurnResult> {
  const payload: SessionTurnRequest = {
    request_id: input.requestId,
    input_text: input.inputText,
  }
  if (input.sessionId !== null) {
    payload.session_id = input.sessionId
  }

  let timedOut = false
  const controller = new AbortController()
  const timer = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, TURN_TIMEOUT_MS)
  const started = performance.now()
  try {
    const response = await fetchImpl('/api/v1/session/turn', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })
    const body = await readJson(response)
    if (!response.ok) {
      return { ok: false, error: mapHttpError(response.status, body) }
    }
    const validated = validateSuccessPayload(body, input.requestId, input.sessionId)
    if ('category' in validated) {
      return { ok: false, error: validated }
    }
    return {
      ok: true,
      response: validated,
      latencyMs: Math.max(0, Math.round(performance.now() - started)),
    }
  } catch {
    if (timedOut) {
      return { ok: false, error: createFrontendError('TIMEOUT') }
    }
    return { ok: false, error: createFrontendError('NETWORK_ERROR') }
  } finally {
    clearTimeout(timer)
  }
}

export type AgentClient = {
  checkHealth: () => Promise<HealthCheckResult>
  sendTurn: (input: SendTurnInput) => Promise<SendTurnResult>
}

export const agentClient: AgentClient = {
  checkHealth: () => checkHealth(),
  sendTurn: (input) => sendTurn(input),
}
