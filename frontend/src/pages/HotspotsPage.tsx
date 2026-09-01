import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowDown, ArrowUp, Car, CheckCircle2, Info, MapPin, TrendingUp } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { TopModeToggle } from '@/components/layout/TopModeToggle'
import { Card } from '@/components/common/Card'
import { PromptChip } from '@/components/common/PromptChip'
import { CrashHotspotMap } from '@/components/maps/CrashHotspotMap'
import { mockReferenceLocations } from '@/data/mock/crashes'
import { getHotspots } from '@/services/analyticsService'
import { HOTSPOTS_SUGGESTED_PROMPTS } from '@/constants/prompts'
import type { HotspotsResponse } from '@/types/analytics'
import { formatDate } from '@/lib/format'

const SUMMARY_ICONS = [MapPin, TrendingUp, Car]

export function HotspotsPage() {
  const navigate = useNavigate()
  const [data, setData] = useState<HotspotsResponse | null>(null)

  useEffect(() => {
    getHotspots().then(setData)
  }, [])

  function handlePromptClick(prompt: string) {
    navigate('/ask/result', { state: { question: prompt } })
  }

  if (!data) {
    return (
      <div className="min-h-screen">
        <PageHeader centerSlot={<TopModeToggle />} />
        <p className="px-8 py-10 text-sm text-text-muted">Loading hotspots...</p>
      </div>
    )
  }

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
            <CrashHotspotMap
              hotspots={data.hotspots}
              referenceLocations={mockReferenceLocations}
              height={440}
              legendCaption={`Data from ${formatDate(data.dataAsOf)}`}
            />
          </Card>

          <Card>
            <h3 className="text-sm font-semibold">Areas with the most crashes</h3>
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
                      <span className="text-text-muted">{area.crashCount.toLocaleString()} crashes</span>
                      <span className={`flex items-center gap-0.5 font-medium ${isWorsening ? 'text-danger' : 'text-positive'}`}>
                        <TrendIcon className="h-3.5 w-3.5" aria-hidden="true" />
                        {Math.abs(area.trend)}%
                      </span>
                    </span>
                  </li>
                )
              })}
            </ul>
          </Card>
        </div>

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

        <div className="grid gap-5 md:grid-cols-2">
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

          <Card className="flex flex-col gap-2">
            <div className="flex items-center gap-2 text-text-muted">
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
              <h3 className="text-sm font-semibold">What the county is focusing on</h3>
            </div>
            <ul className="flex flex-col gap-1.5 text-sm text-text-muted">
              {data.countyFocusAreas.map((item) => (
                <li key={item} className="flex items-start gap-2">
                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-positive" aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
          </Card>
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
