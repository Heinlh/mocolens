import { useNavigate } from 'react-router-dom'
import { Bike, ChevronDown, Landmark, MapPin, PersonStanding, Shield } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { TopModeToggle } from '@/components/layout/TopModeToggle'
import { PromptComposer } from '@/components/chat/PromptComposer'
import { PromptChip } from '@/components/common/PromptChip'
import { ASK_HOME_SUGGESTED_PROMPTS } from '@/constants/prompts'
import { buildAskResultPath } from '@/lib/askRoute'

const PROMPT_ICONS = [PersonStanding, MapPin, Landmark, Bike, Shield]

export function AskHomePage() {
  const navigate = useNavigate()

  function handleAsk(question: string) {
    navigate(buildAskResultPath(question))
  }

  return (
    <div className="flex min-h-screen flex-col">
      <PageHeader centerSlot={<TopModeToggle />} />

      <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-center justify-center gap-8 px-4 py-16 text-center">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-accent">
            Ask questions about Montgomery County traffic safety in plain English.
          </p>
          <h1 className="mt-3 text-3xl font-extrabold tracking-tight md:text-4xl">
            What would you like to understand about road safety in Montgomery County?
          </h1>
        </div>

        <div className="w-full">
          <PromptComposer
            placeholder="Ask anything about crashes, trends, locations, or what the county is doing..."
            onSubmit={handleAsk}
          />
        </div>

        <div className="w-full text-left">
          <p className="mb-3 flex items-center gap-1 text-sm text-text-muted">
            Try one of these
            <ChevronDown className="h-4 w-4" aria-hidden="true" />
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            {ASK_HOME_SUGGESTED_PROMPTS.map((prompt, index) => (
              <PromptChip key={prompt} label={prompt} icon={PROMPT_ICONS[index]} onClick={() => handleAsk(prompt)} />
            ))}
          </div>
        </div>

        <p className="text-xs text-text-muted">MoCoLens combines county data and public reports to explain trends clearly, with sources.</p>
      </div>
    </div>
  )
}
