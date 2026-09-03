/**
 * Resolves answers to natural-language questions and the sidebar's
 * conversation history. `ask` calls the real backend (POST /api/query,
 * the LangGraph agent) using the dynamically configured API origin - its response is
 * already shaped exactly like QueryResponse, same alignment approach as
 * analyticsService.
 *
 * Local development falls back to mock data only when no backend is
 * configured. Production and real HTTP/network failures throw BackendError -
 * silently substituting a fixed demo answer would make unrelated questions
 * appear to return the same evidence.
 */
import { backendFetch, BackendConfigurationError, BackendError } from '@/lib/backendFetch'
import { mockQueryResponse, mockRecentQuestions } from '@/data/mock/conversations'
import { mockSavedInsights } from '@/data/mock/insights'
import type { ConversationEntry, QueryResponse } from '@/types/query'
import type { SavedInsight } from '@/types/insight'

export async function ask(question: string): Promise<QueryResponse> {
  try {
    const res = await backendFetch('/api/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    })
    return (await res.json()) as QueryResponse
  } catch (err) {
    if (import.meta.env.DEV && err instanceof BackendConfigurationError) {
      return { ...mockQueryResponse, question }
    }
    if (err instanceof BackendError) throw err
    throw new BackendError(0, 'The live data service could not be reached. Please try again shortly.')
  }
}

export async function getRecentQuestions(): Promise<ConversationEntry[]> {
  return mockRecentQuestions
}

export async function getSavedInsight(id: string): Promise<SavedInsight | undefined> {
  return mockSavedInsights[id]
}
