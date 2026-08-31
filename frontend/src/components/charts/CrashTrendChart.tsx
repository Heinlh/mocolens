import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { TimeSeriesPoint } from '@/types/analytics'

interface CrashTrendChartProps {
  data: TimeSeriesPoint[]
  seriesLabel?: string
  /** Plain-language chart summary for screen readers, e.g. "Crashes rose from 94 in 2022 to 126 in 2025." */
  description?: string
  height?: number
}

const TOOLTIP_STYLE = {
  background: 'var(--color-surface-elevated-2)',
  border: '1px solid var(--color-border)',
  borderRadius: 8,
  color: 'var(--color-text)',
}

export function CrashTrendChart({ data, seriesLabel = 'Crashes', description, height = 280 }: CrashTrendChartProps) {
  return (
    <div role="img" aria-label={description}>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 8, right: 16, left: -12, bottom: 0 }}>
          <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: 'var(--color-text-muted)', fontSize: 12 }}
            axisLine={{ stroke: 'var(--color-border)' }}
            tickLine={false}
          />
          <YAxis tick={{ fill: 'var(--color-text-muted)', fontSize: 12 }} axisLine={false} tickLine={false} width={40} />
          <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: 'var(--color-text-muted)' }} formatter={(value) => [String(value), seriesLabel]} />
          <Line
            type="monotone"
            dataKey="value"
            name={seriesLabel}
            stroke="var(--color-accent)"
            strokeWidth={2.5}
            dot={{ r: 4, fill: 'var(--color-accent)', strokeWidth: 0 }}
            activeDot={{ r: 6 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
