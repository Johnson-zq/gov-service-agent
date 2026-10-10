import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { presentation } from './content/presentation'
import { App } from './App'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App', () => {
  it('renders the reporting sections and validation wording', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    render(<App />)

    expect(screen.getByRole('heading', { level: 1, name: presentation.hero.title })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: presentation.achievements.title })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: presentation.architecture.title })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: presentation.demo.title })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: presentation.demo.capabilityTitle })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: presentation.roadmap.title })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: presentation.reliability.title })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: presentation.validation.title })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: presentation.next.title })).toBeInTheDocument()
    expect(screen.getAllByText(/77 passed/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/0 failed/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/0 skipped/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/非全仓测试总量/).length).toBeGreaterThan(0)
    expect(screen.getByText(presentation.architecture.disclaimer)).toBeInTheDocument()
    expect(screen.getByText(/不是实时 Trace/)).toBeInTheDocument()

    expect(await screen.findAllByText('Agent 服务当前不可用')).not.toHaveLength(0)
    expect(screen.getByRole('heading', { name: presentation.hero.title })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '实时办理对话' })).toBeInTheDocument()
  })
})
