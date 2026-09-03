import type { QueryResponse } from '@/types/query'
import type { SavedQueryInsight } from '@/types/insight'

const STORAGE_KEY = 'mocolens:saved-insights:v1'
const MAX_SAVED_INSIGHTS = 25

export interface SavedInsightStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
}

function browserStorage(): SavedInsightStorage | undefined {
  if (typeof window === 'undefined') return undefined
  return window.localStorage
}

function isSavedQueryInsight(value: unknown): value is SavedQueryInsight {
  if (!value || typeof value !== 'object') return false
  const item = value as Partial<SavedQueryInsight>
  const response = item.response as Partial<QueryResponse> | undefined
  return (
    typeof item.id === 'string'
    && typeof item.savedAt === 'string'
    && Boolean(response)
    && typeof response?.id === 'string'
    && typeof response.question === 'string'
    && typeof response.answer === 'string'
    && Array.isArray(response.visualizations)
  )
}

export function listSavedInsights(storage: SavedInsightStorage | undefined = browserStorage()): SavedQueryInsight[] {
  if (!storage) return []
  try {
    const parsed: unknown = JSON.parse(storage.getItem(STORAGE_KEY) ?? '[]')
    return Array.isArray(parsed) ? parsed.filter(isSavedQueryInsight) : []
  } catch {
    return []
  }
}

export function getSavedInsight(
  id: string,
  storage: SavedInsightStorage | undefined = browserStorage(),
): SavedQueryInsight | undefined {
  return listSavedInsights(storage).find((insight) => insight.id === id)
}

export function saveInsight(
  response: QueryResponse,
  storage: SavedInsightStorage | undefined = browserStorage(),
): SavedQueryInsight | undefined {
  if (!storage) return undefined
  const insight: SavedQueryInsight = {
    id: response.id,
    savedAt: new Date().toISOString(),
    response,
  }
  const withoutDuplicate = listSavedInsights(storage).filter((saved) => saved.id !== response.id)
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify([insight, ...withoutDuplicate].slice(0, MAX_SAVED_INSIGHTS)))
    return insight
  } catch {
    return undefined
  }
}

export function removeSavedInsight(
  id: string,
  storage: SavedInsightStorage | undefined = browserStorage(),
): void {
  if (!storage) return
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(listSavedInsights(storage).filter((insight) => insight.id !== id)))
  } catch {
    // Storage may be unavailable in privacy mode; there is nothing else to remove.
  }
}

export function isInsightSaved(
  id: string,
  storage: SavedInsightStorage | undefined = browserStorage(),
): boolean {
  return Boolean(getSavedInsight(id, storage))
}
