import { useEffect, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { TopModeToggle } from '@/components/layout/TopModeToggle'
import { Card } from '@/components/common/Card'
import { UserQuestion } from '@/components/chat/UserQuestion'
import { AgentAnswer } from '@/components/chat/AgentAnswer'
import { ask, type AnswerPreview } from '@/services/queryService'
import { BackendConfigurationError, BackendError } from '@/lib/backendFetch'
import type { QueryResponse } from '@/types/query'
import { buildAskResultPath } from '@/lib/askRoute'
import { isInsightSaved, saveInsight } from '@/lib/savedInsights'

const DEFAULT_QUESTION = 'Have pedestrian crashes increased in Silver Spring since 2022?'

/** Plain-language message for any failed question, an unreachable backend
 * included - nothing here falls back to sample data.
 */
function describeError(err: unknown): string {
  if (err instanceof BackendConfigurationError) return err.message
  if (err instanceof BackendError && err.status === 429) {
    return "You're asking questions faster than I can research them. Please wait a moment and try again."
  }
  // 400/422 carry the API's own wording, 0 is "unreachable", 504 is the
  // client-side timeout - all three already read as plain English.
  if (err instanceof BackendError && [0, 400, 422, 502, 504].includes(err.status)) return err.message
  return 'Something went wrong while answering that question. Please try again in a moment.'
}

export function AskResultPage() {
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const stateQuestion = (location.state as { question?: string } | null)?.question
  const question = searchParams.get('q')?.trim() || stateQuestion?.trim() || DEFAULT_QUESTION
  return <AskResult key={question} question={question} />
}

function AskResult({ question }: { question: string }) {
  const navigate = useNavigate()
  const [preview, setPreview] = useState<AnswerPreview | null>(null)
  const [response, setResponse] = useState<QueryResponse | null>(null)
  const [error, setError] = useState<{ question: string; message: string } | null>(null)
  const [savedResponseId, setSavedResponseId] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let target: AnswerPreview = { answer: '', summary: '' }
    let visible = 0
    let frame = 0
    let completed: QueryResponse | undefined

    function paint() {
      frame = 0
      const total = target.answer.length + target.summary.length
      visible = reducedMotion || document.hidden ? total : Math.min(total, visible + Math.max(4, Math.ceil(total / 32)))
      setPreview({
        answer: target.answer.slice(0, visible),
        summary: target.summary.slice(0, Math.max(visible - target.answer.length, 0)),
      })
      if (visible < total) frame = requestAnimationFrame(paint)
      else if (completed) {
        setResponse(completed)
        setSavedResponseId(isInsightSaved(completed.id) ? completed.id : null)
      }
    }
    function progress(next: AnswerPreview) {
      if (controller.signal.aborted) return
      target = next
      if (!frame) paint()
    }
    ask(question, progress, controller.signal).then(
      (result) => {
        completed = result
        progress(result)
      },
      (err) => {
        cancelAnimationFrame(frame)
        if (!controller.signal.aborted) setError({ question, message: describeError(err) })
      },
    )
    return () => {
      controller.abort()
      cancelAnimationFrame(frame)
    }
  }, [question])

  // Avoids briefly showing a stale answer for the previous question while the next one resolves.
  const isShowingCurrentQuestion = response?.question === question
  const currentError = error?.question === question ? error.message : null

  function handleFollowUp(prompt: string) {
    navigate(buildAskResultPath(prompt))
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
        ) : preview?.answer ? (
          <Card>
            <h2 aria-busy="true" className="text-xl font-bold leading-snug md:text-2xl">{preview.answer}</h2>
            <p className="mt-1 text-sm text-text-muted md:text-base">{preview.summary}</p>
          </Card>
        ) : (
          <p role="status" className="text-sm text-text-muted">
            {preview ? 'Checking county data and reports…' : 'Connecting to MoCoLens… The first visit may take a moment.'}
          </p>
        )}
      </div>
    </div>
  )
}
