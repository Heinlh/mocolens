import type { QueryResponse } from './query'

/** A real Ask response saved by the current browser. */
export interface SavedQueryInsight {
  id: string
  savedAt: string
  response: QueryResponse
}
