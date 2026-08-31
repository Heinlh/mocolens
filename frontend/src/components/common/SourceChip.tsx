import { Link } from 'react-router-dom'
import { Database, FileText } from 'lucide-react'
import type { Citation } from '@/types/sources'

interface SourceChipProps {
  citation: Citation
}

/** Pill linking a citation back to the Sources & methodology page (or its own URL, if given). */
export function SourceChip({ citation }: SourceChipProps) {
  const Icon = citation.sourceType === 'dataset' ? Database : FileText

  return (
    <Link
      to={citation.url ?? '/sources'}
      className="inline-flex items-center gap-2 rounded-full border border-border bg-surface-elevated px-3 py-2 text-sm text-text transition-colors hover:border-accent/60 hover:text-accent"
    >
      <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
      <span>{citation.title}</span>
      {citation.page && <span className="text-text-muted">· p.{citation.page}</span>}
    </Link>
  )
}
