/**
 * Resolves provenance for the Sources & Methodology page from the real
 * backend (GET /api/sources): the configured source registry with its
 * actual freshness, and every county document currently searchable by the
 * agent. Nothing here is prototype data.
 *
 * Errors propagate as BackendError so the page reports a failure rather
 * than silently showing a plausible but unrelated source list.
 */
import { backendFetch, BackendError } from '@/lib/backendFetch'
import type { SourcesResponse } from '@/types/sources'

export async function getSources(): Promise<SourcesResponse> {
  try {
    const res = await backendFetch('/api/sources')
    return (await res.json()) as SourcesResponse
  } catch (err) {
    if (err instanceof BackendError) throw err
    throw new BackendError(0, 'The live data service could not be reached. Please try again shortly.')
  }
}
