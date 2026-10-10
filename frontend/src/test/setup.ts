import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

class TestIntersectionObserver {
  readonly root: Element | Document | null = null
  readonly rootMargin = '0px'
  readonly thresholds: ReadonlyArray<number> = [0]

  disconnect(): void {}

  observe(_target: Element): void {}

  takeRecords(): IntersectionObserverEntry[] {
    return []
  }

  unobserve(_target: Element): void {}
}

if (!('IntersectionObserver' in window)) {
  window.IntersectionObserver = TestIntersectionObserver as unknown as typeof IntersectionObserver
}

afterEach(() => {
  cleanup()
  window.sessionStorage.clear()
})
