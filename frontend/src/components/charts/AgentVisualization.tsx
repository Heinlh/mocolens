import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card } from '@/components/common/Card'
import { CrashTrendChart } from '@/components/charts/CrashTrendChart'
import { MiniHotspotMap } from '@/components/maps/MiniHotspotMap'
import type { Hotspot, TimeSeriesPoint } from '@/types/analytics'
import type { VisualizationSpec } from '@/types/visualization'

interface AgentVisualizationProps {
  spec: VisualizationSpec
}

interface XYPoint {
  x: string | number
  y: number
}

function xyPoints(data: Record<string, unknown>): XYPoint[] {
  if (!Array.isArray(data.points)) return []
  return data.points.flatMap((point) => {
    if (!point || typeof point !== 'object') return []
    const value = point as Record<string, unknown>
    if ((typeof value.x !== 'string' && typeof value.x !== 'number') || typeof value.y !== 'number') return []
    return [{ x: value.x, y: value.y }]
  })
}

function dataLabel(data: Record<string, unknown>, camel: string, snake: string, fallback: string): string {
  const value = data[camel] ?? data[snake]
  return typeof value === 'string' && value ? value : fallback
}

function AgentBarChart({ data, label }: { data: TimeSeriesPoint[]; label: string }) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} margin={{ top: 8, right: 12, left: -12, bottom: 24 }}>
        <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ fill: 'var(--color-text-muted)', fontSize: 11 }}
          axisLine={{ stroke: 'var(--color-border)' }}
          tickLine={false}
          interval={0}
          angle={data.length > 4 ? -25 : 0}
          textAnchor={data.length > 4 ? 'end' : 'middle'}
          height={data.length > 4 ? 55 : 30}
        />
        <YAxis tick={{ fill: 'var(--color-text-muted)', fontSize: 12 }} axisLine={false} tickLine={false} width={45} />
        <Tooltip
          contentStyle={{ background: 'var(--color-surface-elevated-2)', border: '1px solid var(--color-border)', borderRadius: 8, color: 'var(--color-text)' }}
          formatter={(value) => [String(value), label]}
          cursor={{ fill: 'var(--color-surface-elevated-2)' }}
        />
        <Bar dataKey="value" name={label} fill="var(--color-accent)" radius={[6, 6, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

function mapHotspots(data: Record<string, unknown>): Hotspot[] {
  if (!Array.isArray(data.points)) return []
  const valid = data.points.flatMap((point, index) => {
    if (!point || typeof point !== 'object') return []
    const value = point as Record<string, unknown>
    if (typeof value.latitude !== 'number' || typeof value.longitude !== 'number') return []
    const weight = typeof value.value === 'number' && Number.isFinite(value.value) ? Math.max(0, value.value) : 1
    return [{ index, latitude: value.latitude, longitude: value.longitude, weight }]
  })
  const maxWeight = Math.max(...valid.map((point) => point.weight), 1)
  return valid.map((point) => ({
    id: `agent-map-${point.index}`,
    area: `Location ${point.index + 1}`,
    latitude: point.latitude,
    longitude: point.longitude,
    crashCount: point.weight,
    trend: 0,
    intensity: point.weight / maxWeight,
  }))
}

export function AgentVisualization({ spec }: AgentVisualizationProps) {
  if (!spec.data) return null
  const data = spec.data

  if (spec.type === 'line' || spec.type === 'bar') {
    const points = xyPoints(data)
    if (points.length === 0) return null
    const chartData = points.map((point) => ({ label: String(point.x), value: point.y }))
    const seriesLabel = dataLabel(data, 'yLabel', 'y_label', 'Value')
    return (
      <Card>
        <h3 className="text-sm font-semibold text-text-muted">{spec.title || 'Results'}</h3>
        <div className="mt-2">
          {spec.type === 'line' ? (
            <CrashTrendChart data={chartData} seriesLabel={seriesLabel} description={spec.title} />
          ) : (
            <AgentBarChart data={chartData} label={seriesLabel} />
          )}
        </div>
      </Card>
    )
  }

  if (spec.type === 'map') {
    const hotspots = mapHotspots(data)
    if (hotspots.length === 0) return null
    return (
      <Card>
        <h3 className="text-sm font-semibold text-text-muted">{spec.title || 'Mapped results'}</h3>
        <div className="mt-2">
          <MiniHotspotMap hotspots={hotspots} centerLabel="Montgomery County" />
        </div>
      </Card>
    )
  }

  if (spec.type === 'kpi') {
    const label = typeof data.label === 'string' ? data.label : spec.title || 'Result'
    const value = typeof data.value === 'number' || typeof data.value === 'string' ? data.value : null
    if (value === null) return null
    return (
      <Card>
        <p className="text-sm text-text-muted">{label}</p>
        <p className="mt-2 text-3xl font-bold tracking-tight">{typeof value === 'number' ? value.toLocaleString() : value}</p>
      </Card>
    )
  }

  if (spec.type === 'table') {
    const headers = Array.isArray(data.headers) ? data.headers.map(String) : []
    const rows = Array.isArray(data.rows) ? data.rows.filter(Array.isArray) : []
    if (headers.length === 0 || rows.length === 0) return null
    const totalRows = data.totalRows ?? data.total_rows
    return (
      <Card>
        <h3 className="text-sm font-semibold text-text-muted">{spec.title || 'Results'}</h3>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-border">
                {headers.map((header) => <th key={header} className="px-2 py-2 font-semibold text-text">{header}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex} className="border-b border-border/60 last:border-0">
                  {row.map((cell, cellIndex) => <td key={cellIndex} className="px-2 py-2 text-text-muted">{String(cell ?? '—')}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data.truncated === true && <p className="mt-2 text-xs text-text-muted">Showing {rows.length} of {String(totalRows ?? 'more')} rows.</p>}
      </Card>
    )
  }

  return null
}
