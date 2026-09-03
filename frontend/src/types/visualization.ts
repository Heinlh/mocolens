export type VisualizationType = 'line' | 'bar' | 'donut' | 'map' | 'kpi' | 'table'

/** Describes a backend-selected visualization for the current answer. */
export interface VisualizationSpec {
  id: string
  type: VisualizationType
  title: string
  /** Backend-generated payload. Its shape depends on `type` and is
   * validated by AgentVisualization before rendering.
   */
  data?: Record<string, unknown> | null
}
