import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowDown, ArrowUp, Car, CheckCircle2, ExternalLink, Info, MapPin, TrendingUp } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { TopModeToggle } from '@/components/layout/TopModeToggle'
import { PageStatus } from '@/components/layout/PageStatus'
import { describeLoadError } from '@/lib/backendFetch'
import { Card } from '@/components/common/Card'
import { EmptyState } from '@/components/common/EmptyState'
import { PromptChip } from '@/components/common/PromptChip'
import { CrashHotspotMap } from '@/components/maps/CrashHotspotMap'
import { COUNTY_REFERENCE_LOCATIONS } from '@/constants/referenceLocations'
import { getHotspots } from '@/services/analyticsService'
import { HOTSPOTS_SUGGESTED_PROMPTS } from '@/constants/prompts'
import type { HotspotsResponse } from '@/types/analytics'
import { formatDate } from '@/lib/format'
import { buildAskResultPath } from '@/lib/askRoute'

const SUMMARY_ICONS = [MapPin, TrendingUp, Car]

export function HotspotsPage() {
  const navigate = useNavigate()
  const [data, setData] = useState<HotspotsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isCurrent = true
    getHotspots().then(
      (result) => {
        if (isCurrent) setData(result)
      },
      (err) => {
        if (isCurrent) setError(describeLoadError(err, 'Crash hotspots'))
      },
    )
    return () => {
      isCurrent = false
    }
  }, [])

  function handlePromptClick(prompt: string) {
    navigate(buildAskResultPath(prompt))
  }

  if (error) return <PageStatus message={error} tone="error" />
  if (!data) return <PageStatus message="Loading hotspots..." />

  const hasHotspots = data.hotspots.length > 0

  return (
    <div className="min-h-screen">
      <PageHeader
        centerSlot={<TopModeToggle />}
        title="Crash hotspots in Montgomery County"
        subtitle="See where crashes are most concentrated and what they may mean."
      />

      <div className="flex flex-col gap-6 px-4 py-6 md:px-8">
        <div className="grid gap-5 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            {hasHotspots ? (
              <CrashHotspotMap
                hotspots={data.hotspots}
                referenceLocations={COUNTY_REFERENCE_LOCATIONS}
                numberedMarkers
                height={440}
                legendCaption={`Data as of ${formatDate(data.dataAsOf)}`}
              />
            ) : (
              <EmptyState
                icon={MapPin}
                title="Not enough crashes to map"
                description="No location in the county reached the threshold for a hotspot over this period."
              />
            )}
          </Card>

          <Card>
            <h3 className="text-sm font-semibold">Locations with the most crashes</h3>
            <p className="mt-0.5 text-xs text-text-muted">
              Each location covers about half a mile, named for its main road.
            </p>
            <ul className="mt-3 flex flex-col gap-1">
              {data.rankedAreas.map((area) => {
                const isWorsening = area.trend > 0
                const TrendIcon = isWorsening ? ArrowUp : ArrowDown
                return (
                  <li key={area.rank} className="flex items-center justify-between gap-2 rounded-lg px-2 py-2 hover:bg-surface-elevated-2">
                    <span className="flex items-center gap-3">
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-elevated-2 text-xs font-semibold text-text-muted">
                        {area.rank}
                      </span>
                      <span className="text-sm font-medium text-text">{area.name}</span>
                    </span>
                    <span className="flex items-center gap-3 text-sm">
                      <span className="whitespace-nowrap text-text-muted">{area.crashCount.toLocaleString()} crashes</span>
                      {area.trend === 0 ? null : (
                        <span className={`flex items-center gap-0.5 font-medium ${isWorsening ? 'text-danger' : 'text-positive'}`}>
                          <TrendIcon className="h-3.5 w-3.5" aria-hidden="true" />
                          {Math.abs(area.trend)}%
                        </span>
                      )}
                    </span>
                  </li>
                )
              })}
            </ul>
          </Card>
        </div>

        {data.summaryCards.length > 0 ? (
          <div className="grid gap-5 md:grid-cols-3">
            {data.summaryCards.map((card, index) => {
              const Icon = SUMMARY_ICONS[index] ?? MapPin
              return (
                <Card key={card.label} className="flex flex-col gap-1">
                  <div className="flex items-center gap-1.5 text-text-muted">
                    <Icon className="h-4 w-4" aria-hidden="true" />
                    <span className="text-xs font-medium">{card.label}</span>
                  </div>
                  <p className="text-xl font-bold text-text">{card.primaryText}</p>
                  <p className="text-sm text-text-muted">{card.secondaryText}</p>
                </Card>
              )
            })}
          </div>
        ) : null}

        <div className="grid items-start gap-5 md:grid-cols-2">
          <Card className="flex flex-col gap-2">
            <div className="flex items-center gap-2 text-text-muted">
              <Info className="h-4 w-4" aria-hidden="true" />
              <h3 className="text-sm font-semibold">How to read this map</h3>
            </div>
            <p className="text-sm text-text-muted">Brighter areas show where crashes happen more often.</p>
            <p className="text-sm text-text-muted">
              More crashes don&apos;t always mean higher risk per person - some places simply have more people and traffic.
            </p>
          </Card>

          {/* Quoted from county reports rather than written here, so the
              panel says what the county said, with a link to check it. */}
          {data.countyFocus.length > 0 ? (
            <Card className="flex flex-col gap-3">
              <div className="flex items-center gap-2 text-text-muted">
                <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                <h3 className="text-sm font-semibold">What county reports say the county is focusing on</h3>
              </div>
              <ul className="flex flex-col gap-3">
                {data.countyFocus.map((item) => (
                  <li key={`${item.documentTitle}-${item.page}-${item.title}`} className="flex flex-col gap-1">
                    <p className="text-sm font-medium text-text">{item.title}</p>
                    <p className="text-sm text-text-muted">{item.excerpt}</p>
                    {item.url ? (
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex w-fit items-center gap-1 text-xs text-accent underline-offset-2 hover:underline"
                      >
                        {item.documentTitle}
                        {item.page ? `, p. ${item.page}` : ''}
                        <ExternalLink className="h-3 w-3" aria-hidden="true" />
                      </a>
                    ) : null}
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}
        </div>

        <div>
          <h3 className="mb-2 text-sm font-semibold text-text-muted">Try one of these</h3>
          <div className="grid gap-2 sm:grid-cols-3">
            {HOTSPOTS_SUGGESTED_PROMPTS.map((prompt) => (
              <PromptChip key={prompt} label={prompt} onClick={() => handlePromptClick(prompt)} />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
