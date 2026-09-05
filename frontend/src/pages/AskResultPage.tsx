import { useEffect, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { TopModeToggle } from '@/components/layout/TopModeToggle'
import { Card } from '@/components/common/Card'
import { UserQuestion } from '@/components/chat/UserQuestion'
import { AgentAnswer } from '@/components/chat/AgentAnswer'
import { ask } from '@/services/queryService'
import { BackendConfigurationError, BackendError } from '@/lib/backendFetch'
import type { QueryResponse } from '@/types/query'
import { buildAskResultPath } from '@/lib/askRoute'
import { isInsightSaved, saveInsight } from '@/lib/savedInsights'

const DEFAULT_QUESTION = 'Have pedestrian crashes increased in Silver Spring since 2022?'

/** Plain-language message for a real (reachable-backend) rejection - never
 * shown for "backend unreachable", which falls back to mock data instead
 * and never reaches this component as an error at all.
 */
function describeError(err: unknown): string {
  if (err instanceof BackendConfigurationError) return err.message
  if (err instanceof BackendError && err.status === 429) {
    return "You're asking questions faster than I can research them. Please wait a moment and try again."
  }
  // 400/422 carry the API's own wording, 0 is "unreachable", 504 is the
  // client-side timeout - all three already read as plain English.
  if (err instanceof BackendError && [0, 400, 422, 504].includes(err.status)) return err.message
  return 'Something went wrong while answering that question. Please try again in a moment.'
}

export function AskResultPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const stateQuestion = (location.state as { question?: string } | null)?.question
  const question = searchParams.get('q')?.trim() || stateQuestion?.trim() || DEFAULT_QUESTION

  const [response, setResponse] = useState<QueryResponse | null>(null)
  const [error, setError] = useState<{ question: string; message: string } | null>(null)
  const [savedResponseId, setSavedResponseId] = useState<string | null>(null)

  useEffect(() => {
    let isCurrent = true
    ask(question).then(
      (result) => {
        if (isCurrent) {
          setError(null)
          setResponse(result)
          setSavedResponseId(isInsightSaved(result.id) ? result.id : null)
        }
      },
      (err) => {
        if (isCurrent) setError({ question, message: describeError(err) })
      },
    )
    return () => {
      isCurrent = false
    }
  }, [question])

  // Avoids briefly showing a stale answer for the previous question while the next one resolves.
  const isShowingCurrentQuestion = response?.question === question
  const currentError = error?.question === question ? error.message : null

  function handleFollowUp(prompt: string) {
    navigate(buildAskResultPath(prompt), { replace: true })
  }

  function handleSave(result: QueryResponse) {
    const saved = saveInsight(result)
    if (saved) setSavedResponseId(saved.id)
  }

  return (
    <div className="min-h-screen">
      <PageHeader centerSlot={<TopModeToggle />} />
      <div className="mx-auto flex max-w-4xl flex-col gap-5 px-4 py-6 md:px-8">
        <UserQuestion question={question} askedAt="Just now" />
        {currentError ? (
          <Card className="flex items-start gap-3">
            <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-danger/15 text-danger">
              <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            </span>
            <p className="text-sm text-text">{currentError}</p>
          </Card>
        ) : response && isShowingCurrentQuestion ? (
          <AgentAnswer
            response={response}
            onFollowUpClick={handleFollowUp}
            onSave={handleSave}
            isSaved={savedResponseId === response.id}
          />
        ) : (
          <p className="text-sm text-text-muted">Thinking...</p>
        )}
      </div>
    </div>
  )
}
