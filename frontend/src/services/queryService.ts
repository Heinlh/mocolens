/**
 * Resolves answers to natural-language questions and the sidebar's
 * conversation history. `ask` calls the real backend (POST /api/query,
 * the LangGraph agent) when VITE_API_BASE_URL is set - its response is
 * already shaped exactly like QueryResponse, same alignment approach as
 * analyticsService.
 *
 * Falls back to mock data only when the backend is unreachable/unconfigured
 * (the standalone-demo case). A reachable backend that rejects the request
 * (rate limited, real error) throws BackendError instead - the caller must
 * show that to the user. Silently substituting a fake answer for a real
 * rejection would mean the chat is lying about giving a real answer.
 */
import { backendFetch, isBackendConfigured, BackendError } from '@/lib/backendFetch'
import { mockQueryResponse, mockRecentQuestions } from '@/data/mock/conversations'
import { mockSavedInsights } from '@/data/mock/insights'
import type { ConversationEntry, QueryResponse } from '@/types/query'
import type { SavedInsight } from '@/types/insight'

export async function ask(question: string): Promise<QueryResponse> {
  if (!isBackendConfigured()) return { ...mockQueryResponse, question }

  try {
    const res = await backendFetch('/api/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    })
    return (await res.json()) as QueryResponse
  } catch (err) {
    if (err instanceof BackendError) throw err
    console.error('Backend unreachable, falling back to mock query response:', err)
    return { ...mockQueryResponse, question }
  }
}

export async function getRecentQuestions(): Promise<ConversationEntry[]> {
  return mockRecentQuestions
}

export async function getSavedInsight(id: string): Promise<SavedInsight | undefined> {
  return mockSavedInsights[id]
}
