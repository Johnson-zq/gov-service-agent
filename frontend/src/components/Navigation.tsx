import { presentation } from '../content/presentation'

const LINKS = [
  { href: '#overview', label: '总览' },
  { href: '#architecture', label: '架构' },
  { href: '#demo', label: '实时交互' },
  { href: '#roadmap', label: '路线' },
  { href: '#validation', label: '验证' },
  { href: '#next', label: '下一步' },
] as const

export function Navigation() {
  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3">
        <a href="#overview" className="text-sm font-semibold text-gov-800">
          {presentation.productName}
        </a>
        <nav aria-label="页面区域">
          <ul className="flex flex-wrap items-center gap-1">
            {LINKS.map((link) => (
              <li key={link.href}>
                <a
                  href={link.href}
                  className="rounded-md px-3 py-2 text-sm text-slate-700 hover:bg-gov-50 hover:text-gov-800"
                >
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </header>
  )
}
