export const INPUT_MAX_LENGTH = 4000

export type SessionTurnRequest = {
  request_id: string
  session_id?: string
  input_text: string
}

export type SessionStatus = 'COMPLETED' | 'AWAITING_USER_INPUT'

export type SessionTurnSuccess = {
  session_id: string
  request_id: string
  status: SessionStatus
  response_text: string
  requires_user_input: boolean
}

export type SessionTurnError = {
  request_id: string | null
  session_id: string | null
  status: 'FAILED'
  error: {
    code: string
    message: string
  }
}

export type HealthResponse = {
  status: 'ok'
}

export type HealthState = 'UNKNOWN' | 'CHECKING' | 'AVAILABLE' | 'UNAVAILABLE'

export type ChatMessage = {
  local_id: string
  role: 'user' | 'assistant'
  text: string
  request_id: string
  created_at: string
  latency_ms?: number
  status?: SessionStatus
  requires_user_input?: boolean
}

export type PendingRequest = {
  requestId: string
  inputText: string
  sessionIdAtDispatch: string | null
  startedAt: string
}

export type FrontendErrorCategory =
  | 'NETWORK_ERROR'
  | 'TIMEOUT'
  | 'INVALID_REQUEST'
  | 'SESSION_NOT_FOUND'
  | 'SESSION_EXPIRED'
  | 'REQUEST_ID_REUSE_CONFLICT'
  | 'REQUEST_IN_PROGRESS'
  | 'AGENT_FAILURE'
  | 'PERSISTENCE_UNAVAILABLE'
  | 'INVALID_RESPONSE'
  | 'UNKNOWN_ERROR'

export type FrontendError = {
  category: FrontendErrorCategory
  message: string
  retryable: boolean
  httpStatus?: number
}
