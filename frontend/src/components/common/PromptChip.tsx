import type { LucideIcon } from 'lucide-react'
import { ArrowRight } from 'lucide-react'

interface PromptChipProps {
  label: string
  icon?: LucideIcon
  onClick: () => void
}

/** Clickable suggested-question card used on the Ask home, follow-ups, and hotspot prompts. */
export function PromptChip({ label, icon: Icon, onClick }: PromptChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex w-full items-center justify-between gap-3 rounded-xl border border-border bg-surface-elevated px-4 py-3 text-left text-sm text-text transition-colors hover:border-accent/60 hover:bg-surface-elevated-2"
    >
      <span className="flex items-center gap-2">
        {Icon && <Icon className="h-4 w-4 shrink-0 text-accent" aria-hidden="true" />}
        {label}
      </span>
      <ArrowRight
        className="h-4 w-4 shrink-0 text-text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-accent"
        aria-hidden="true"
      />
    </button>
  )
}
