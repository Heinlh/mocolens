import type { LucideIcon } from 'lucide-react'
import { ArrowDown, ArrowUp, Minus } from 'lucide-react'
import type { Metric } from '@/types/analytics'
import { Card } from './Card'

type MetricTone = 'accent' | 'danger' | 'neutral'

interface MetricCardProps {
  metric: Metric
  icon?: LucideIcon
  tone?: MetricTone
}

const TONE_CLASSES: Record<MetricTone, string> = {
  accent: 'bg-accent/15 text-accent',
  danger: 'bg-danger/15 text-danger',
  neutral: 'bg-surface-elevated-2 text-text-muted',
}

/**
 * KPI card. Change is always shown as an arrow icon + signed text (never
 * color alone) so the direction reads even without color perception.
 */
export function MetricCard({ metric, icon: Icon, tone = 'accent' }: MetricCardProps) {
  const hasChange = metric.change !== undefined
  const ArrowIcon = metric.changeDirection === 'up' ? ArrowUp : metric.changeDirection === 'down' ? ArrowDown : Minus
  const changeColorClass =
    metric.changeIsPositive === true ? 'text-positive' : metric.changeIsPositive === false ? 'text-danger' : 'text-text-muted'

  return (
    <Card className="flex items-start justify-between gap-4">
      <div>
        <p className="text-sm text-text-muted">{metric.label}</p>
        <p className="mt-2 text-3xl font-bold tracking-tight">{metric.value}</p>
        {hasChange ? (
          <p className={`mt-1 flex items-center gap-1 text-sm font-medium ${changeColorClass}`}>
            <ArrowIcon className="h-3.5 w-3.5" aria-hidden="true" />
            <span>
              {Math.abs(metric.change ?? 0)}% {metric.description ?? ''}
            </span>
          </p>
        ) : (
          metric.description && <p className="mt-1 text-sm text-text-muted">{metric.description}</p>
        )}
      </div>
      {Icon && (
        <div className={`shrink-0 rounded-full p-2.5 ${TONE_CLASSES[tone]}`}>
          <Icon className="h-5 w-5" aria-hidden="true" />
        </div>
      )}
    </Card>
  )
}
