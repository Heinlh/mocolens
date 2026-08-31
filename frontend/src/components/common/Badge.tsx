import type { ReactNode } from 'react'

type BadgeVariant = 'accent' | 'neutral' | 'danger' | 'positive'

interface BadgeProps {
  children: ReactNode
  variant?: BadgeVariant
}

const VARIANT_CLASSES: Record<BadgeVariant, string> = {
  accent: 'bg-accent/15 text-accent',
  neutral: 'bg-surface-elevated-2 text-text-muted',
  danger: 'bg-danger/15 text-danger',
  positive: 'bg-positive/15 text-positive',
}

export function Badge({ children, variant = 'neutral' }: BadgeProps) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${VARIANT_CLASSES[variant]}`}>
      {children}
    </span>
  )
}
