/**
 * Resolves answers to natural-language questions and the sidebar's
 * conversation history. `ask` calls the real backend (POST /api/query,
 * the LangGraph agent) when VITE_API_BASE_URL is set - its response is
 * already shaped exactly like QueryResponse, same alignment approach as
 * analyticsService. Falls back to mock data if the backend is
 * unreachable/unconfigured, so the frontend still runs standalone.
 */
import { mockQueryResponse, mockRecentQuestions } from '@/data/mock/conversations'
import { mockSavedInsights } from '@/data/mock/insights'
import type { ConversationEntry, QueryResponse } from '@/types/query'
import type { SavedInsight } from '@/types/insight'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL as string | undefined

export async function ask(question: string): Promise<QueryResponse> {
  if (!API_BASE_URL) return { ...mockQueryResponse, question }

  try {
    const res = await fetch(`${API_BASE_URL}/api/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    })
    if (!res.ok) throw new Error(`query request failed: ${res.status}`)
    return (await res.json()) as QueryResponse
  } catch (err) {
    console.error('Falling back to mock query response:', err)
    return { ...mockQueryResponse, question }
  }
}

export async function getRecentQuestions(): Promise<ConversationEntry[]> {
  return mockRecentQuestions
}

export async function getSavedInsight(id: string): Promise<SavedInsight | undefined> {
  return mockSavedInsights[id]
}
