import type { ChatMessage, PendingRequest, SessionStatus } from '../api/contracts'

export const SESSION_ID_KEY = 'gov-agent-demo:v1:session-id'
export const MESSAGES_KEY = 'gov-agent-demo:v1:messages'
export const PENDING_KEY = 'gov-agent-demo:v1:pending-request'

export type DemoPersistence = {
  sessionId: string | null
  messages: ChatMessage[]
  pendingRequest: PendingRequest | null
}

function browserSessionStorage(): Storage | null {
  try {
    return window.sessionStorage
  } catch {
    return null
  }
}

function readRaw(key: string): string | null {
  try {
    return browserSessionStorage()?.getItem(key) ?? null
  } catch {
    return null
  }
}

function writeRaw(key: string, value: string): void {
  try {
    browserSessionStorage()?.setItem(key, value)
  } catch {
    // Persistence is best-effort. The page continues without it.
  }
}

function removeKey(key: string): void {
  try {
    browserSessionStorage()?.removeItem(key)
  } catch {
    // Ignore storage failures.
  }
}

function parseStored(key: string): unknown {
  const raw = readRaw(key)
  if (raw === null) return undefined
  try {
    return JSON.parse(raw) as unknown
  } catch {
    removeKey(key)
    return undefined
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isSessionStatus(value: unknown): value is SessionStatus {
  return value === 'COMPLETED' || value === 'AWAITING_USER_INPUT'
}

function isChatMessage(value: unknown): value is ChatMessage {
  if (!isRecord(value)) return false
  if (typeof value.local_id !== 'string' || value.local_id.length === 0) return false
  if (value.role !== 'user' && value.role !== 'assistant') return false
  if (typeof value.text !== 'string') return false
  if (typeof value.request_id !== 'string' || value.request_id.length === 0) return false
  if (typeof value.created_at !== 'string') return false
  if (value.latency_ms !== undefined && typeof value.latency_ms !== 'number') return false
  if (value.status !== undefined && !isSessionStatus(value.status)) return false
  if (
    value.requires_user_input !== undefined &&
    typeof value.requires_user_input !== 'boolean'
  ) {
    return false
  }
  return true
}

function isPendingRequest(value: unknown): value is PendingRequest {
  if (!isRecord(value)) return false
  if (typeof value.requestId !== 'string' || value.requestId.length === 0) return false
  if (typeof value.inputText !== 'string') return false
  if (value.sessionIdAtDispatch !== null && typeof value.sessionIdAtDispatch !== 'string') {
    return false
  }
  if (typeof value.startedAt !== 'string' || value.startedAt.length === 0) return false
  return true
}

export function loadDemoPersistence(): DemoPersistence {
  const sessionParsed = parseStored(SESSION_ID_KEY)
  let sessionId: string | null = null
  if (typeof sessionParsed === 'string' && sessionParsed.trim().length > 0) {
    sessionId = sessionParsed
  } else if (sessionParsed !== undefined) {
    removeKey(SESSION_ID_KEY)
  }

  const messagesParsed = parseStored(MESSAGES_KEY)
  let messages: ChatMessage[] = []
  if (Array.isArray(messagesParsed) && messagesParsed.every(isChatMessage)) {
    messages = messagesParsed
  } else if (messagesParsed !== undefined) {
    removeKey(MESSAGES_KEY)
  }

  const pendingParsed = parseStored(PENDING_KEY)
  let pendingRequest: PendingRequest | null = null
  if (isPendingRequest(pendingParsed)) {
    pendingRequest = pendingParsed
  } else if (pendingParsed !== undefined) {
    removeKey(PENDING_KEY)
  }

  return { sessionId, messages, pendingRequest }
}

export function saveDemoPersistence(state: DemoPersistence): void {
  if (state.sessionId && state.sessionId.trim().length > 0) {
    writeRaw(SESSION_ID_KEY, JSON.stringify(state.sessionId))
  } else {
    removeKey(SESSION_ID_KEY)
  }

  if (state.messages.length > 0) {
    writeRaw(MESSAGES_KEY, JSON.stringify(state.messages))
  } else {
    removeKey(MESSAGES_KEY)
  }

  if (state.pendingRequest) {
    writeRaw(PENDING_KEY, JSON.stringify(state.pendingRequest))
  } else {
    removeKey(PENDING_KEY)
  }
}

export function clearDemoPersistence(): void {
  removeKey(SESSION_ID_KEY)
  removeKey(MESSAGES_KEY)
  removeKey(PENDING_KEY)
}
