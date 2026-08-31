import { useLocation, useNavigate } from 'react-router-dom'

const MODES = [
  { key: 'ask', label: 'Ask', path: '/ask' },
  { key: 'explore', label: 'Explore', path: '/dashboard' },
] as const

/** Segmented Ask/Explore control. Active state follows the current route prefix. */
export function TopModeToggle() {
  const navigate = useNavigate()
  const location = useLocation()
  const activeKey = location.pathname.startsWith('/dashboard') ? 'explore' : 'ask'

  return (
    <div role="tablist" aria-label="View mode" className="inline-flex rounded-full border border-border bg-surface-elevated p-1">
      {MODES.map((mode) => {
        const isActive = mode.key === activeKey
        return (
          <button
            key={mode.key}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => navigate(mode.path)}
            className={`rounded-full px-5 py-1.5 text-sm font-semibold transition-colors ${
              isActive ? 'bg-accent text-black' : 'text-text-muted hover:text-text'
            }`}
          >
            {mode.label}
          </button>
        )
      })}
    </div>
  )
}
