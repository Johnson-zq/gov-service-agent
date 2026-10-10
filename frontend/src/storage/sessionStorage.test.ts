import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ChatMessage, PendingRequest } from '../api/contracts'
import {
  MESSAGES_KEY,
  PENDING_KEY,
  SESSION_ID_KEY,
  clearDemoPersistence,
  loadDemoPersistence,
  saveDemoPersistence,
} from './sessionStorage'

const message: ChatMessage = {
  local_id: 'local-1',
  role: 'user',
  text: '已保存的问题',
  request_id: 'req-1',
  created_at: '2026-01-01T00:00:00.000Z',
}

const pending: PendingRequest = {
  requestId: 'req-1',
  inputText: '已保存的问题',
  sessionIdAtDispatch: null,
  startedAt: '2026-01-01T00:00:00.000Z',
}

describe('demo persistence', () => {
  beforeEach(() => {
    window.sessionStorage.clear()
  })

  it('saves and loads the session id, messages, and pending request', () => {
    saveDemoPersistence({
      sessionId: 'server-session',
      messages: [message],
      pendingRequest: pending,
    })
    expect(loadDemoPersistence()).toEqual({
      sessionId: 'server-session',
      messages: [message],
      pendingRequest: pending,
    })
  })

  it('clears every demo key', () => {
    saveDemoPersistence({
      sessionId: 'server-session',
      messages: [message],
      pendingRequest: pending,
    })
    clearDemoPersistence()
    expect(loadDemoPersistence()).toEqual({
      sessionId: null,
      messages: [],
      pendingRequest: null,
    })
    expect(window.sessionStorage.getItem(SESSION_ID_KEY)).toBeNull()
    expect(window.sessionStorage.getItem(MESSAGES_KEY)).toBeNull()
    expect(window.sessionStorage.getItem(PENDING_KEY)).toBeNull()
  })

  it('drops corrupt JSON and returns a safe default', () => {
    window.sessionStorage.setItem(MESSAGES_KEY, '{')
    expect(loadDemoPersistence().messages).toEqual([])
    expect(window.sessionStorage.getItem(MESSAGES_KEY)).toBeNull()
  })

  it('drops values that parse but do not match the expected shape', () => {
    window.sessionStorage.setItem(SESSION_ID_KEY, '15')
    window.sessionStorage.setItem(PENDING_KEY, JSON.stringify({ requestId: '' }))
    const loaded = loadDemoPersistence()
    expect(loaded.sessionId).toBeNull()
    expect(loaded.pendingRequest).toBeNull()
    expect(window.sessionStorage.getItem(SESSION_ID_KEY)).toBeNull()
    expect(window.sessionStorage.getItem(PENDING_KEY)).toBeNull()
  })

  it('does not read or write localStorage', () => {
    const setItem = vi.spyOn(window.localStorage, 'setItem')
    const getItem = vi.spyOn(window.localStorage, 'getItem')
    saveDemoPersistence({ sessionId: 'server-session', messages: [message], pendingRequest: null })
    loadDemoPersistence()
    expect(setItem).not.toHaveBeenCalled()
    expect(getItem).not.toHaveBeenCalled()
    setItem.mockRestore()
    getItem.mockRestore()
  })
})
