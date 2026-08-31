import { PromptChip } from '@/components/common/PromptChip'

interface SuggestedPromptsProps {
  prompts: string[]
  onSelect: (prompt: string) => void
}

export function SuggestedPrompts({ prompts, onSelect }: SuggestedPromptsProps) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {prompts.map((prompt) => (
        <PromptChip key={prompt} label={prompt} onClick={() => onSelect(prompt)} />
      ))}
    </div>
  )
}
