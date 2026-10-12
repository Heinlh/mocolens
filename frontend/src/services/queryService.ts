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

export async function ask(question: string): Promise<QueryResponse> {
  if (DEMO_MODE) return { ...mockQueryResponse, question }
  try {
    const res = await backendFetch('/api/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    })
    return (await res.json()) as QueryResponse
  } catch (err) {
    if (err instanceof BackendError) throw err
    throw new BackendError(0, 'The live data service could not be reached. Please try again shortly.')
  }
}
