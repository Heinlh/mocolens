import { User } from 'lucide-react'

interface UserQuestionProps {
  question: string
  askedAt?: string
}

export function UserQuestion({ question, askedAt }: UserQuestionProps) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-card border border-border bg-surface-elevated px-4 py-3">
      <div className="flex items-center gap-3">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent/15 text-accent">
          <User className="h-4 w-4" aria-hidden="true" />
        </span>
        <p className="text-sm font-medium text-text">{question}</p>
      </div>
      {askedAt && <span className="shrink-0 text-xs text-text-muted">{askedAt}</span>}
    </div>
  )
}
