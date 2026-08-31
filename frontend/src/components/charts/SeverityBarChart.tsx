import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { CategoryValue } from '@/types/analytics'

interface SeverityBarChartProps {
  data: CategoryValue[]
  description?: string
  height?: number
}

export function SeverityBarChart({ data, description, height = 280 }: SeverityBarChartProps) {
  return (
    <div role="img" aria-label={description}>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 8, right: 12, left: -12, bottom: 24 }}>
          <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }}
            axisLine={{ stroke: 'var(--color-border)' }}
            tickLine={false}
            interval={0}
            angle={-25}
            textAnchor="end"
            height={50}
          />
          <YAxis tick={{ fill: 'var(--color-text-muted)', fontSize: 12 }} axisLine={false} tickLine={false} width={40} />
          <Tooltip
            contentStyle={{ background: 'var(--color-surface-elevated-2)', border: '1px solid var(--color-border)', borderRadius: 8, color: 'var(--color-text)' }}
            cursor={{ fill: 'var(--color-surface-elevated-2)' }}
          />
          <Bar dataKey="value" fill="var(--color-accent)" radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
