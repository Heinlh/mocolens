/**
 * Resolves source/methodology data for the Sources & Methodology page.
 * Swap for `fetch("/api/sources")` once the backend exists.
 */
import { mockSourcesResponse } from '@/data/mock/sources'
import type { SourcesResponse } from '@/types/sources'

export async function getSources(): Promise<SourcesResponse> {
  return mockSourcesResponse
}
