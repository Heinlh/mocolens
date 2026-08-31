import type { ReactNode } from 'react'

interface CardProps {
  children: ReactNode
  className?: string
}

/** Base panel used throughout the app - rounded, flat, subtly elevated. */
export function Card({ children, className = '' }: CardProps) {
  return <div className={`rounded-card border border-border bg-surface-elevated p-5 ${className}`}>{children}</div>
}
