import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { UseAgentChatResult } from '../hooks/useAgentChat'
import { presentation } from '../content/presentation'
import { AgentDemoSection } from './AgentDemoSection'

const chatBox = vi.hoisted(() => ({
  current: null as UseAgentChatResult | null,
}))

vi.mock('../hooks/useAgentChat', () => ({
  useAgentChat: () => chatBox.current,
}))

function chat(overrides: Partial<UseAgentChatResult> = {}): UseAgentChatResult {
  return {
    serverSessionId: null,
    messages: [],
    pendingRequest: null,
    isSending: false,
    transportError: null,
    sessionInvalid: false,
    unconfirmed: false,
    sendMessage: vi.fn().mockResolvedValue(true),
    retry: vi.fn().mockResolvedValue(undefined),
    requestNewSession: vi.fn(),
    ...overrides,
  }
}

describe('AgentDemoSection', () => {
  beforeEach(() => {
    chatBox.current = chat()
  })

  it('renders the chat shell and capability panel', () => {
    render(<AgentDemoSection health="AVAILABLE" />)
    expect(screen.getByRole('heading', { name: '实时办理对话' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: presentation.demo.capabilityTitle })).toBeInTheDocument()
    expect(screen.getByText(presentation.demo.empty)).toBeInTheDocument()
  })

  it('fills the example question without sending it', async () => {
    const user = userEvent.setup()
    render(<AgentDemoSection health="AVAILABLE" />)
    await user.click(screen.getByRole('button', { name: '填入示例问题' }))
    expect(screen.getByLabelText('办理问题')).toHaveValue(presentation.exampleQuestion)
    expect(chatBox.current?.sendMessage).not.toHaveBeenCalled()
  })

  it('sends the current draft from the button and from Enter', async () => {
    const user = userEvent.setup()
    render(<AgentDemoSection health="AVAILABLE" />)
    await user.type(screen.getByLabelText('办理问题'), '咨询办理')
    await user.click(screen.getByRole('button', { name: '发送' }))
    expect(chatBox.current?.sendMessage).toHaveBeenCalledWith('咨询办理')

    chatBox.current = chat()
    render(<AgentDemoSection health="AVAILABLE" />)
    const field = screen.getAllByLabelText('办理问题')[1]
    if (!field) throw new Error('缺少第二个输入框')
    await user.type(field, '键盘发送')
    await user.keyboard('{Enter}')
    expect(chatBox.current?.sendMessage).toHaveBeenCalledWith('键盘发送')
  })

  it('inserts a newline for Shift+Enter and does not send', async () => {
    const user = userEvent.setup()
    render(<AgentDemoSection health="AVAILABLE" />)
    const field = screen.getByLabelText('办理问题')
    await user.type(field, '第一行')
    await user.keyboard('{Shift>}{Enter}{/Shift}')
    expect(field).toHaveValue('第一行\n')
    expect(chatBox.current?.sendMessage).not.toHaveBeenCalled()
  })

  it('limits the field to 4000 characters', () => {
    render(<AgentDemoSection health="AVAILABLE" />)
    expect(screen.getByLabelText('办理问题')).toHaveAttribute('maxlength', '4000')
  })

  it('disables sending and shows the loading text while a request is in flight', async () => {
    const user = userEvent.setup()
    chatBox.current = chat()
    const view = render(<AgentDemoSection health="AVAILABLE" />)
    await user.type(screen.getByLabelText('办理问题'), '处理中')
    chatBox.current = chat({ isSending: true })
    view.rerender(<AgentDemoSection health="AVAILABLE" />)
    expect(screen.getByRole('button', { name: '发送' })).toBeDisabled()
    expect(screen.getByText(presentation.loading)).toBeInTheDocument()
  })

  it('shows awaiting and completed hints, latency, and the short session id', () => {
    chatBox.current = chat({
      serverSessionId: 'abcdef12-3456-4789-a012-3456789abcde',
      messages: [
        {
          local_id: 'm1',
          role: 'assistant',
          text: '请补充参保地',
          request_id: 'req-1',
          created_at: '2026-01-01T00:00:00.000Z',
          status: 'AWAITING_USER_INPUT',
          requires_user_input: true,
          latency_ms: 1500,
        },
      ],
    })
    const view = render(<AgentDemoSection health="AVAILABLE" />)
    expect(screen.getByText(presentation.awaitingHint)).toBeInTheDocument()
    expect(screen.getByText('本次请求耗时 1.5 s')).toBeInTheDocument()
    expect(screen.getByText('会话 abcdef12')).toBeInTheDocument()

    chatBox.current = chat({
      messages: [
        {
          local_id: 'm2',
          role: 'assistant',
          text: '本轮已完成',
          request_id: 'req-2',
          created_at: '2026-01-01T00:00:00.000Z',
          status: 'COMPLETED',
          requires_user_input: false,
          latency_ms: 80,
        },
      ],
    })
    view.rerender(<AgentDemoSection health="AVAILABLE" />)
    expect(screen.getByText(presentation.completedHint)).toBeInTheDocument()
    expect(screen.getByText('本次请求耗时 80 ms')).toBeInTheDocument()
  })

  it('shows the transport error, retry action, and new-session action', async () => {
    const user = userEvent.setup()
    chatBox.current = chat({
      pendingRequest: {
        requestId: 'req-1',
        inputText: '刚才的问题',
        sessionIdAtDispatch: null,
        startedAt: '2026-01-01T00:00:00.000Z',
      },
      transportError: {
        category: 'TIMEOUT',
        message: '请求超时，请稍后重试。',
        retryable: true,
      },
    })
    render(<AgentDemoSection health="UNAVAILABLE" />)
    expect(screen.getByRole('alert')).toHaveTextContent('请求超时，请稍后重试。')
    await user.click(screen.getByRole('button', { name: '重试' }))
    await user.click(screen.getByRole('button', { name: '新建会话' }))
    expect(chatBox.current?.retry).toHaveBeenCalledTimes(1)
    expect(chatBox.current?.requestNewSession).toHaveBeenCalledTimes(1)
  })
})
