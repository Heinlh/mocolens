import { useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { ArrowUp, Mic, Paperclip, SlidersHorizontal } from 'lucide-react'

interface PromptComposerProps {
  placeholder?: string
  onSubmit: (question: string) => void
}

export function PromptComposer({ placeholder = 'Ask a question...', onSubmit }: PromptComposerProps) {
  const [value, setValue] = useState('')

  function submit() {
    const trimmed = value.trim()
    if (!trimmed) return
    onSubmit(trimmed)
    setValue('')
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    submit()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-2xl border border-border bg-surface-elevated p-3 shadow-sm">
      <label htmlFor="prompt-composer-input" className="sr-only">
        Ask a question about Montgomery County traffic safety
      </label>
      <textarea
        id="prompt-composer-input"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        rows={2}
        className="w-full resize-none bg-transparent px-2 py-1 text-base text-text placeholder:text-text-muted focus:outline-none"
      />
      <div className="mt-2 flex items-center justify-between px-1">
        <div className="flex items-center gap-1 text-text-muted">
          <button type="button" aria-label="Attach a file" className="rounded-lg p-2 transition-colors hover:bg-surface-elevated-2 hover:text-text">
            <Paperclip className="h-4 w-4" aria-hidden="true" />
          </button>
          <button type="button" aria-label="Filters" className="rounded-lg p-2 transition-colors hover:bg-surface-elevated-2 hover:text-text">
            <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <div className="flex items-center gap-1">
          <button type="button" aria-label="Voice input" className="rounded-lg p-2 text-text-muted transition-colors hover:bg-surface-elevated-2 hover:text-text">
            <Mic className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            type="submit"
            aria-label="Submit question"
            disabled={!value.trim()}
            className="rounded-full bg-accent p-2 text-black transition-colors hover:bg-accent-dark disabled:cursor-not-allowed disabled:opacity-40"
          >
            <ArrowUp className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </div>
    </form>
  )
}
