export type VisualizationType = 'line' | 'bar' | 'donut' | 'map' | 'kpi' | 'table'

/** Describes a visualization the answer used, for backend-driven rendering later. */
export interface VisualizationSpec {
  id: string
  type: VisualizationType
  title: string
}
