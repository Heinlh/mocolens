import type { ReactNode } from 'react'
import { HelpCircle } from 'lucide-react'

interface PageHeaderProps {
  title?: string
  subtitle?: string
  actions?: ReactNode
  centerSlot?: ReactNode
  leadingSlot?: ReactNode
}

/**
 * Shared top chrome: a bar with an optional centered slot (the Ask/Explore
 * toggle) plus a persistent help/avatar cluster, and an optional
 * title/subtitle/actions row underneath for pages that need one.
 */
export function PageHeader({ title, subtitle, actions, centerSlot, leadingSlot }: PageHeaderProps) {
  return (
    <header className="border-b border-border">
      <div className="flex items-center justify-between gap-4 px-4 py-3 md:px-8">
        <div className="min-w-0 flex-1">{leadingSlot}</div>
        <div className="flex flex-1 justify-center">{centerSlot}</div>
        <div className="flex flex-1 items-center justify-end gap-3">
          <button
            type="button"
            aria-label="Help"
            className="rounded-full p-2 text-text-muted transition-colors hover:bg-surface-elevated hover:text-text"
          >
            <HelpCircle className="h-5 w-5" aria-hidden="true" />
          </button>
          <span
            aria-hidden="true"
            className="flex h-8 w-8 items-center justify-center rounded-full bg-danger text-xs font-semibold text-white"
          >
            HH
          </span>
        </div>
      </div>

      {title && (
        <div className="px-4 py-5 md:px-8">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold tracking-tight md:text-3xl">{title}</h1>
              {subtitle && <p className="mt-1 text-sm text-text-muted md:text-base">{subtitle}</p>}
            </div>
            {actions && <div className="flex items-center gap-2">{actions}</div>}
          </div>
        </div>
      )}
    </header>
  )
}
