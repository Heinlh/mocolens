import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import type { CategoryValue } from '@/types/analytics'

interface RoadUserDonutChartProps {
  data: CategoryValue[]
  centerLabel?: string
  centerValue?: string | number
  description?: string
  height?: number
}

const DEFAULT_COLORS = ['var(--color-accent)', 'var(--color-danger)', 'var(--color-chart-cyclist)', 'var(--color-chart-passenger)']

/** Just the donut + center readout. Pages compose their own legend list beside it. */
export function RoadUserDonutChart({ data, centerLabel, centerValue, description, height = 220 }: RoadUserDonutChartProps) {
  return (
    <div role="img" aria-label={description} className="relative">
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="label" innerRadius="65%" outerRadius="95%" paddingAngle={2} stroke="none">
            {data.map((entry, index) => (
              <Cell key={entry.label} fill={entry.color ?? DEFAULT_COLORS[index % DEFAULT_COLORS.length]} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{ background: 'var(--color-surface-elevated-2)', border: '1px solid var(--color-border)', borderRadius: 8, color: 'var(--color-text)' }}
            formatter={(value, name) => [`${value}%`, name]}
          />
        </PieChart>
      </ResponsiveContainer>
      {(centerLabel || centerValue !== undefined) && (
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          {centerValue !== undefined && <span className="text-2xl font-bold">{centerValue}</span>}
          {centerLabel && <span className="text-xs text-text-muted">{centerLabel}</span>}
        </div>
      )}
    </div>
  )
}
