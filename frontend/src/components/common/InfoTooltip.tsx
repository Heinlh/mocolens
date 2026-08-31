import { useState } from 'react'
import { Info } from 'lucide-react'

interface InfoTooltipProps {
  label: string
}

/** Click-to-toggle info popover (not hover-only, so it stays keyboard operable). */
export function InfoTooltip({ label }: InfoTooltipProps) {
  const [open, setOpen] = useState(false)

  return (
    <span className="relative inline-flex">
      <button
        type="button"
        aria-label="More information"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        onBlur={() => setOpen(false)}
        className="text-text-muted transition-colors hover:text-accent"
      >
        <Info className="h-4 w-4" aria-hidden="true" />
      </button>
      {open && (
        <span
          role="tooltip"
          className="absolute left-1/2 top-full z-10 mt-2 w-56 -translate-x-1/2 rounded-lg border border-border bg-surface-elevated-2 p-2.5 text-xs text-text-muted shadow-lg"
        >
          {label}
        </span>
      )}
    </span>
  )
}
