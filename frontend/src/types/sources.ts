export type SourceType = 'dataset' | 'report'

export interface Citation {
  id: string
  title: string
  sourceType: SourceType
  url?: string
  page?: string
  /** ISO date, or a bare 4-digit year when only the publication year is known. */
  publishedAt?: string
}

/** One entry from the backend's source registry (GET /api/sources). */
export interface DataSource {
  id: string
  title: string
  description: string
  sourceType: SourceType
  /** How often the source is refreshed, e.g. "weekly". Absent if the registry does not say. */
  refreshCadence?: string
  /** YYYY-MM-DD. Absent when nothing has been ingested for this source yet. */
  lastUpdated?: string
  url?: string
}

export interface MethodologyStep {
  step: number
  title: string
  description: string
}

export interface Caveat {
  id: string
  title: string
  description: string
}

/** GET /api/sources. Page copy (methodology steps, caveats) is not part of
 * this contract - it describes the product, not the data, so it lives with
 * the page in @/constants/methodology. There is no single dataAsOf here on
 * purpose: each source carries its own lastUpdated, because the crash
 * tables and the report index are refreshed independently.
 */
export interface SourcesResponse {
  sources: DataSource[]
  citations: Citation[]
  /** Number of report passages currently searchable by the agent. */
  indexedChunkCount: number
}
