export type SourceType = 'dataset' | 'report'

export interface Citation {
  id: string
  title: string
  sourceType: SourceType
  url?: string
  page?: string
  publishedAt?: string
}

export type DataSourceIcon = 'car' | 'users' | 'footprints' | 'fileText'

export interface DataSource {
  id: string
  title: string
  description: string
  icon: DataSourceIcon
  refreshCadence: string
  lastUpdated: string
  type: SourceType
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

export interface SourcesResponse {
  sources: DataSource[]
  methodologySteps: MethodologyStep[]
  citations: Citation[]
  caveats: Caveat[]
}
