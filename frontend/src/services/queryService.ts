/**
 * Resolves answers to natural-language questions and the sidebar's
 * conversation history.
 * Swap `ask` for `fetch("/api/query", { method: "POST", body: JSON.stringify({ question }) })`
 * once the backend agent exists. The prototype always resolves the same
 * mocked answer regardless of the question text.
 */
import { mockQueryResponse, mockRecentQuestions } from '@/data/mock/conversations'
import { mockSavedInsights } from '@/data/mock/insights'
import type { ConversationEntry, QueryResponse } from '@/types/query'
import type { SavedInsight } from '@/types/insight'

export async function ask(question: string): Promise<QueryResponse> {
  return { ...mockQueryResponse, question }
}

export async function getRecentQuestions(): Promise<ConversationEntry[]> {
  return mockRecentQuestions
}

export async function getSavedInsight(id: string): Promise<SavedInsight | undefined> {
  return mockSavedInsights[id]
}
