import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { PageHeader } from '@/components/layout/PageHeader'
import { TopModeToggle } from '@/components/layout/TopModeToggle'
import { UserQuestion } from '@/components/chat/UserQuestion'
import { AgentAnswer } from '@/components/chat/AgentAnswer'
import { ask } from '@/services/queryService'
import type { QueryResponse } from '@/types/query'

const DEFAULT_QUESTION = 'Have pedestrian crashes increased in Silver Spring since 2022?'

export function AskResultPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const question = (location.state as { question?: string } | null)?.question ?? DEFAULT_QUESTION

  const [response, setResponse] = useState<QueryResponse | null>(null)

  useEffect(() => {
    let isCurrent = true
    ask(question).then((result) => {
      if (isCurrent) setResponse(result)
    })
    return () => {
      isCurrent = false
    }
  }, [question])

  // Avoids briefly showing a stale answer for the previous question while the next one resolves.
  const isShowingCurrentQuestion = response?.question === question

  function handleFollowUp(prompt: string) {
    navigate('/ask/result', { state: { question: prompt }, replace: true })
  }

  return (
    <div className="min-h-screen">
      <PageHeader centerSlot={<TopModeToggle />} />
      <div className="mx-auto flex max-w-4xl flex-col gap-5 px-4 py-6 md:px-8">
        <UserQuestion question={question} askedAt="Just now" />
        {response && isShowingCurrentQuestion ? (
          <AgentAnswer response={response} onFollowUpClick={handleFollowUp} />
        ) : (
          <p className="text-sm text-text-muted">Thinking...</p>
        )}
      </div>
    </div>
  )
}
