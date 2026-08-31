import { useState } from 'react'
import type { ReactNode } from 'react'
import { Menu, X } from 'lucide-react'
import { Sidebar } from './Sidebar'

interface AppShellProps {
  children: ReactNode
}

/** Persistent sidebar on desktop; an off-canvas drawer (toggled from a mobile top bar) below md. */
export function AppShell({ children }: AppShellProps) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  return (
    <div className="min-h-screen bg-bg text-text">
      <div className="flex items-center justify-between border-b border-border px-4 py-3 md:hidden">
        <button
          type="button"
          onClick={() => setMobileNavOpen(true)}
          aria-label="Open navigation"
          className="rounded-lg p-2 text-text-muted hover:bg-surface-elevated hover:text-text"
        >
          <Menu className="h-5 w-5" aria-hidden="true" />
        </button>
        <span className="text-sm font-semibold">MoCoLens</span>
        <span className="w-9" aria-hidden="true" />
      </div>

      <div className="flex">
        <div className="hidden md:block">
          <Sidebar />
        </div>

        {mobileNavOpen && (
          <div className="fixed inset-0 z-40 md:hidden">
            <button
              type="button"
              aria-label="Close navigation"
              className="absolute inset-0 bg-black/60"
              onClick={() => setMobileNavOpen(false)}
            />
            <div className="absolute inset-y-0 left-0 border-r border-border bg-bg">
              <button
                type="button"
                onClick={() => setMobileNavOpen(false)}
                aria-label="Close navigation"
                className="absolute right-2 top-2 z-10 rounded-lg p-2 text-text-muted hover:bg-surface-elevated hover:text-text"
              >
                <X className="h-5 w-5" aria-hidden="true" />
              </button>
              <Sidebar onNavigate={() => setMobileNavOpen(false)} />
            </div>
          </div>
        )}

        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  )
}
