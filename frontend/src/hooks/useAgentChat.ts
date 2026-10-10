import { useRef, useState } from 'react'
import { agentClient, type AgentClient, type SendTurnInput } from '../api/agentClient'
import {
  INPUT_MAX_LENGTH,
  type ChatMessage,
  type FrontendError,
  type PendingRequest,
} from '../api/contracts'
import { presentation } from '../content/presentation'
import {
  clearDemoPersistence,
  loadDemoPersistence,
  saveDemoPersistence,
} from '../storage/sessionStorage'

export type UseAgentChatResult = {
  serverSessionId: string | null
  messages: ChatMessage[]
  pendingRequest: PendingRequest | null
  isSending: boolean
  transportError: FrontendError | null
  sessionInvalid: boolean
  unconfirmed: boolean
  sendMessage: (rawInput: string) => Promise<boolean>
  retry: () => Promise<void>
  requestNewSession: () => void
}

function createId(): string {
  return crypto.randomUUID()
}

export function useAgentChat(client: AgentClient = agentClient): UseAgentChatResult {
  const [serverSessionId, setServerSessionId] = useState<string | null>(
    () => loadDemoPersistence().sessionId,
  )
  const [messages, setMessages] = useState<ChatMessage[]>(
    () => loadDemoPersistence().messages,
  )
  const [pendingRequest, setPendingRequest] = useState<PendingRequest | null>(
    () => loadDemoPersistence().pendingRequest,
  )
  const [isSending, setIsSending] = useState(false)
  const [transportError, setTransportError] = useState<FrontendError | null>(null)
  const [sessionInvalid, setSessionInvalid] = useState(false)
  const [unconfirmed, setUnconfirmed] = useState(
    () => loadDemoPersistence().pendingRequest !== null,
  )

  const isSendingRef = useRef(false)
  const sessionInvalidRef = useRef(false)
  const serverSessionIdRef = useRef(serverSessionId)
  const messagesRef = useRef(messages)
  const pendingRef = useRef(pendingRequest)

  serverSessionIdRef.current = serverSessionId
  messagesRef.current = messages
  pendingRef.current = pendingRequest
  sessionInvalidRef.current = sessionInvalid

  function persist(
    nextPending: PendingRequest | null,
    nextMessages: ChatMessage[],
    nextSessionId: string | null,
  ) {
    saveDemoPersistence({
      sessionId: nextSessionId,
      messages: nextMessages,
      pendingRequest: nextPending,
    })
  }

  async function dispatch(pending: PendingRequest, appendUser: boolean): Promise<void> {
    if (isSendingRef.current || sessionInvalidRef.current) return

    isSendingRef.current = true
    setIsSending(true)
    setTransportError(null)

    let nextMessages = messagesRef.current
    if (appendUser) {
      const userMessage: ChatMessage = {
        local_id: createId(),
        role: 'user',
        text: pending.inputText,
        request_id: pending.requestId,
        created_at: new Date().toISOString(),
      }
      nextMessages = [...nextMessages, userMessage]
      messagesRef.current = nextMessages
      setMessages(nextMessages)
    }

    pendingRef.current = pending
    setPendingRequest(pending)
    persist(pending, nextMessages, serverSessionIdRef.current)

    const input: SendTurnInput = {
      requestId: pending.requestId,
      inputText: pending.inputText,
      sessionId: pending.sessionIdAtDispatch,
    }
    const result = await client.sendTurn(input)

    isSendingRef.current = false
    setIsSending(false)

    if (!result.ok) {
      setTransportError(result.error)
      if (
        result.error.category === 'SESSION_NOT_FOUND' ||
        result.error.category === 'SESSION_EXPIRED'
      ) {
        sessionInvalidRef.current = true
        setSessionInvalid(true)
      }
      const keptPending = result.error.retryable ? pending : null
      pendingRef.current = keptPending
      setPendingRequest(keptPending)
      persist(keptPending, messagesRef.current, serverSessionIdRef.current)
      return
    }

    if (pending.sessionIdAtDispatch === null) {
      serverSessionIdRef.current = result.response.session_id
      setServerSessionId(result.response.session_id)
    }

    const assistant: ChatMessage = {
      local_id: createId(),
      role: 'assistant',
      text: result.response.response_text,
      request_id: result.response.request_id,
      created_at: new Date().toISOString(),
      latency_ms: result.latencyMs,
      status: result.response.status,
      requires_user_input: result.response.requires_user_input,
    }
    const withAssistant = [...messagesRef.current, assistant]
    messagesRef.current = withAssistant
    setMessages(withAssistant)
    pendingRef.current = null
    setPendingRequest(null)
    setTransportError(null)
    setUnconfirmed(false)
    persist(null, withAssistant, serverSessionIdRef.current)
  }

  async function sendMessage(rawInput: string): Promise<boolean> {
    if (isSendingRef.current || sessionInvalidRef.current) return false
    const inputText = rawInput.trim()
    if (inputText.length === 0 || inputText.length > INPUT_MAX_LENGTH) return false
    setUnconfirmed(false)
    const pending: PendingRequest = {
      requestId: createId(),
      inputText,
      sessionIdAtDispatch: serverSessionIdRef.current,
      startedAt: new Date().toISOString(),
    }
    await dispatch(pending, true)
    return true
  }

  async function retry(): Promise<void> {
    if (isSendingRef.current || sessionInvalidRef.current) return
    const pending = pendingRef.current
    if (!pending) return
    await dispatch(pending, false)
  }

  function reset(): void {
    serverSessionIdRef.current = null
    messagesRef.current = []
    pendingRef.current = null
    sessionInvalidRef.current = false
    setServerSessionId(null)
    setMessages([])
    setPendingRequest(null)
    setTransportError(null)
    setSessionInvalid(false)
    setUnconfirmed(false)
    clearDemoPersistence()
  }

  function requestNewSession(): void {
    if (isSendingRef.current) return
    if (messagesRef.current.length > 0) {
      const confirmed = window.confirm(presentation.newSessionConfirm)
      if (!confirmed) return
    }
    reset()
  }

  return {
    serverSessionId,
    messages,
    pendingRequest,
    isSending,
    transportError,
    sessionInvalid,
    unconfirmed,
    sendMessage,
    retry,
    requestNewSession,
  }
}
