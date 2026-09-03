import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Landmark, Shield } from 'lucide-react'
import { NEW_QUESTION_ICON, NEW_QUESTION_PATH, SIDEBAR_NAV_ITEMS } from '@/constants/navigation'
import { getRecentQuestions } from '@/services/queryService'
import type { ConversationEntry } from '@/types/query'
import { buildAskResultPath } from '@/lib/askRoute'

interface SidebarProps {
  /** Called after any navigating action - used to close the mobile drawer. */
  onNavigate?: () => void
}

export function Sidebar({ onNavigate }: SidebarProps) {
  const location = useLocation()
  const navigate = useNavigate()
  const [recentQuestions, setRecentQuestions] = useState<ConversationEntry[]>([])
  const NewQuestionIcon = NEW_QUESTION_ICON

  useEffect(() => {
    getRecentQuestions().then(setRecentQuestions)
  }, [])

  function handleNewQuestion() {
    navigate(NEW_QUESTION_PATH)
    onNavigate?.()
  }

  function handleRecentQuestionClick(question: string) {
    navigate(buildAskResultPath(question))
    onNavigate?.()
  }

  return (
    <aside className="flex h-screen w-72 flex-col overflow-y-auto border-r border-border bg-bg px-4 py-5">
      <Link to="/" onClick={onNavigate} className="flex items-center gap-2.5 px-1">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent/15 text-accent">
          <Landmark className="h-5 w-5" aria-hidden="true" />
        </span>
        <span>
          <span className="block text-lg font-extrabold leading-tight">MoCoLens</span>
          <span className="block text-[10px] font-semibold uppercase tracking-wide text-accent">
            See it. Understand it. Save lives.
          </span>
        </span>
      </Link>

      <button
        type="button"
        onClick={handleNewQuestion}
        className="mt-5 flex items-center justify-center gap-2 rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-black transition-colors hover:bg-accent-dark"
      >
        <NewQuestionIcon className="h-4 w-4" aria-hidden="true" />
        New question
      </button>

      <nav className="mt-5 flex flex-col gap-1" aria-label="Primary">
        {SIDEBAR_NAV_ITEMS.map((item) => {
          const basePath = '/' + item.path.split('/')[1]
          const isActive = location.pathname.startsWith(basePath)
          const Icon = item.icon
          return (
            <Link
              key={item.path}
              to={item.path}
              onClick={onNavigate}
              aria-current={isActive ? 'page' : undefined}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                isActive ? 'bg-surface-elevated text-text' : 'text-text-muted hover:bg-surface-elevated hover:text-text'
              }`}
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              {item.label}
            </Link>
          )
        })}
      </nav>

      <div className="mt-6">
        <div className="flex items-center justify-between px-1">
          <span className="text-xs font-semibold uppercase tracking-wide text-text-muted">Recent questions</span>
          <Link to="/dashboard" className="text-xs font-medium text-accent hover:underline">
            View all
          </Link>
        </div>
        <ul className="mt-2 flex flex-col gap-0.5">
          {recentQuestions.map((entry) => (
            <li key={entry.id}>
              <button
                type="button"
                onClick={() => handleRecentQuestionClick(entry.question)}
                className="flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-sm text-text-muted transition-colors hover:bg-surface-elevated hover:text-text"
              >
                <span className="truncate">{entry.question}</span>
                <span className="shrink-0 text-xs text-text-muted">{entry.askedAt}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-6 flex-1" />

      <div className="rounded-card border border-danger/40 bg-danger/10 p-4">
        <div className="flex items-center gap-2">
          <Shield className="h-4 w-4 text-danger" aria-hidden="true" />
          <p className="text-sm font-semibold text-text">Every crash is preventable.</p>
        </div>
        <p className="mt-1 text-sm font-medium text-accent">Together, we can save lives.</p>
      </div>

      {/* Generic placeholder attribution - no official county seal asset supplied. */}
      <div className="mt-4 flex items-center gap-2 px-1 text-xs text-text-muted">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-surface-elevated-2">
          <Landmark className="h-3.5 w-3.5" aria-hidden="true" />
        </span>
        <span>
          Montgomery County, MD
          <br />
          Department of Transportation
          <br />
          by Hein Htet
        </span>
      </div>
    </aside>
  )
}
