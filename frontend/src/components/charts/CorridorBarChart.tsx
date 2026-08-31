import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { CorridorStat } from '@/types/insight'

interface CorridorBarChartProps {
  data: CorridorStat[]
  description?: string
  height?: number
}

export function CorridorBarChart({ data, description, height = 220 }: CorridorBarChartProps) {
  return (
    <div role="img" aria-label={description}>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 32, left: 8, bottom: 4 }}>
          <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" tick={{ fill: 'var(--color-text-muted)', fontSize: 12 }} axisLine={false} tickLine={false} />
          <YAxis
            type="category"
            dataKey="corridor"
            tick={{ fill: 'var(--color-text-muted)', fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            width={140}
          />
          <Tooltip
            contentStyle={{ background: 'var(--color-surface-elevated-2)', border: '1px solid var(--color-border)', borderRadius: 8, color: 'var(--color-text)' }}
            cursor={{ fill: 'var(--color-surface-elevated-2)' }}
          />
          <Bar dataKey="crashCount" name="Crashes" fill="var(--color-accent)" radius={[0, 6, 6, 0]}>
            <LabelList dataKey="crashCount" position="right" fill="var(--color-text)" fontSize={12} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
