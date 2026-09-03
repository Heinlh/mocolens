import { CheckCircle2, PersonStanding, ShieldCheck, TrendingUp, Users2 } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { QueryResponse } from '@/types/query'
import { Card } from '@/components/common/Card'
import { MetricCard } from '@/components/common/MetricCard'
import { SourceChip } from '@/components/common/SourceChip'
import { PromptChip } from '@/components/common/PromptChip'
import { CrashTrendChart } from '@/components/charts/CrashTrendChart'
import { MiniHotspotMap } from '@/components/maps/MiniHotspotMap'
import { AgentVisualization } from '@/components/charts/AgentVisualization'

interface AgentAnswerProps {
  response: QueryResponse
  onFollowUpClick: (prompt: string) => void
}

const METRIC_ICONS: LucideIcon[] = [PersonStanding, PersonStanding, TrendingUp]
const METRIC_TONES: Array<'accent' | 'danger' | 'neutral'> = ['accent', 'danger', 'danger']

/** The full agent response: headline, KPIs, chart + mini map, plain-language context, sources, follow-ups. */
export function AgentAnswer({ response, onFollowUpClick }: AgentAnswerProps) {
  const liveVisualizations = response.visualizations.filter((visualization) => visualization.data)
  const showLegacyMockVisuals = liveVisualizations.length === 0 && (response.metrics.length > 0 || response.crashTrend.length > 0 || response.hotspots.length > 0)

  return (
    <div className="flex flex-col gap-5">
      <Card className="flex flex-col gap-4">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-positive/15 text-positive">
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-xl font-bold leading-snug md:text-2xl">{response.answer}</h2>
            <p className="mt-1 text-sm text-text-muted md:text-base">{response.summary}</p>
          </div>
        </div>

        {showLegacyMockVisuals && response.metrics.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-3">
            {response.metrics.map((metric, index) => (
              <MetricCard key={metric.label} metric={metric} icon={METRIC_ICONS[index]} tone={METRIC_TONES[index]} />
            ))}
          </div>
        )}
      </Card>

      {liveVisualizations.length > 0 && (
        <div className="grid gap-5 lg:grid-cols-2">
          {liveVisualizations.map((visualization) => (
            <AgentVisualization key={visualization.id} spec={visualization} />
          ))}
        </div>
      )}

      {showLegacyMockVisuals && (response.crashTrend.length > 0 || response.hotspots.length > 0) && (
        <div className="grid gap-5 lg:grid-cols-2">
          {response.crashTrend.length > 0 && (
            <Card>
              <h3 className="text-sm font-semibold text-text-muted">Pedestrian crashes over time</h3>
              <div className="mt-2">
                <CrashTrendChart data={response.crashTrend} description={response.summary} />
              </div>
            </Card>
          )}
          {response.hotspots.length > 0 && (
            <Card>
              <h3 className="text-sm font-semibold text-text-muted">Where crashes are concentrated</h3>
              <div className="mt-2">
                <MiniHotspotMap hotspots={response.hotspots} centerLabel="Silver Spring" />
              </div>
            </Card>
          )}
        </div>
      )}

      <div className={`grid gap-5 ${response.countyReportPoints.length > 0 ? 'lg:grid-cols-2' : ''}`}>
        <Card className="flex flex-col gap-2">
          <div className="flex items-center gap-2 text-text-muted">
            <Users2 className="h-4 w-4" aria-hidden="true" />
            <h3 className="text-sm font-semibold">What the data means</h3>
          </div>
          <p className="text-sm text-text-muted">{response.whatDataMeans}</p>
        </Card>
        {response.countyReportPoints.length > 0 && (
          <Card className="flex flex-col gap-2">
            <div className="flex items-center gap-2 text-text-muted">
              <ShieldCheck className="h-4 w-4" aria-hidden="true" />
              <h3 className="text-sm font-semibold">What county reports say</h3>
            </div>
            <ul className="flex flex-col gap-1.5 text-sm text-text-muted">
              {response.countyReportPoints.map((point) => (
                <li key={point} className="flex gap-2">
                  <span aria-hidden="true">•</span>
                  {point}
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>

      {response.limitations && response.limitations.length > 0 && (
        <p className="text-xs text-text-muted">Caveats: {response.limitations.join(' ')}</p>
      )}

      {response.citations.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-text-muted">Sources</h3>
          <div className="flex flex-wrap gap-2">
            {response.citations.map((citation) => (
              <SourceChip key={citation.id} citation={citation} />
            ))}
          </div>
        </div>
      )}

      <div>
        <h3 className="mb-2 text-sm font-semibold text-text-muted">Try one of these</h3>
        <div className="grid gap-2 sm:grid-cols-3">
          {response.followUpPrompts.map((prompt) => (
            <PromptChip key={prompt} label={prompt} onClick={() => onFollowUpClick(prompt)} />
          ))}
        </div>
      </div>
    </div>
  )
}
