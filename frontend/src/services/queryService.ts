/**
 * Resolves answers to natural-language questions. `ask` calls the real
 * backend (POST /api/query, the LangGraph agent) using the dynamically
 * configured API origin - its response is already shaped exactly like
 * QueryResponse, same alignment approach as analyticsService.
 *
 * A sample answer is returned only in DEMO_MODE (local dev, no backend
 * configured), where the whole app is labelled as a demo. Production and
 * real HTTP/network failures throw BackendError - silently substituting a
 * fixed demo answer would make unrelated questions appear to return the
 * same evidence.
 */
import { backendFetch, BackendError, DEMO_MODE } from '@/lib/backendFetch'
import { mockQueryResponse } from '@/data/mock/conversations'
import type { QueryResponse } from '@/types/query'

export type AnswerPreview = { answer: string; summary: string }
type StreamEvent =
  | { type: 'ready' }
  | ({ type: 'text' } & AnswerPreview)
  | { type: 'done'; response: QueryResponse }
  | { type: 'error'; message: string }

let lastWarmup = 0
export function warmAskBackend() {
  if (DEMO_MODE || Date.now() - lastWarmup < 60_000) return
  lastWarmup = Date.now()
  void backendFetch('/api/health', { cache: 'no-store' }).catch(() => {})
}

async function readAnswer(res: Response, onProgress: (preview: AnswerPreview) => void) {
  if (!res.body) throw new Error('Missing response body')
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  try {
    while (true) {
      const chunk = await reader.read()
      if (chunk.done) throw new BackendError(502, 'The answer was interrupted. Please try again.')
      buffer += chunk.value
      let end = buffer.indexOf('\n')
      while (end >= 0) {
        const event: StreamEvent = JSON.parse(buffer.slice(0, end))
        buffer = buffer.slice(end + 1)
        if (event.type === 'error') throw new BackendError(502, event.message)
        if (event.type === 'done') return event.response
        if (event.type === 'ready') onProgress({ answer: '', summary: '' })
        if (event.type === 'text') onProgress(event)
        end = buffer.indexOf('\n')
      }
    }
  } finally {
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}

// Answers already shown in this tab, so Back and Forward re-show one instead of
// asking again - a repeat request still counts against the API's per-minute limit.
// ponytail: unbounded per tab; a visit asks a handful of questions.
const answered = new Map<string, QueryResponse>()

export async function ask(
  question: string, onProgress?: (preview: AnswerPreview) => void, signal?: AbortSignal,
): Promise<QueryResponse> {
  if (DEMO_MODE) return { ...mockQueryResponse, question }
  const seen = answered.get(question)
  if (seen) return seen
  const result = await fetchAnswer(question, onProgress, signal)
  answered.set(question, result)
  return result
}

async function fetchAnswer(
  question: string, onProgress?: (preview: AnswerPreview) => void, signal?: AbortSignal,
): Promise<QueryResponse> {
  try {
    const res = await backendFetch('/api/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: onProgress ? 'application/x-ndjson' : 'application/json' },
      body: JSON.stringify({ question }),
      signal,
    })
    if (onProgress && res.headers.get('Content-Type')?.includes('application/x-ndjson')) {
      return await readAnswer(res, onProgress)
    }
    return (await res.json()) as QueryResponse
  } catch (err) {
    if (err instanceof BackendError) throw err
    throw new BackendError(0, 'The live data service could not be reached. Please try again shortly.')
  }
}
