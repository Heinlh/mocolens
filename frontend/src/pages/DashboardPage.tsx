import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, Bike, Car, PersonStanding, RefreshCw, ShieldAlert } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { TopModeToggle } from '@/components/layout/TopModeToggle'
import { Card } from '@/components/common/Card'
import { MetricCard } from '@/components/common/MetricCard'
import { InfoTooltip } from '@/components/common/InfoTooltip'
import { CrashTrendChart } from '@/components/charts/CrashTrendChart'
import { SeverityBarChart } from '@/components/charts/SeverityBarChart'
import { RoadUserDonutChart } from '@/components/charts/RoadUserDonutChart'
import { CrashHotspotMap } from '@/components/maps/CrashHotspotMap'
import { mockReferenceLocations } from '@/data/mock/crashes'
import { getDashboardOverview } from '@/services/analyticsService'
import { BackendError } from '@/lib/backendFetch'
import type { DashboardFilters, DashboardResponse } from '@/types/analytics'
import { formatDate } from '@/lib/format'

const METRIC_ICONS: LucideIcon[] = [Car, PersonStanding, Bike, ShieldAlert]
const METRIC_TONES: Array<'accent' | 'danger' | 'neutral'> = ['accent', 'accent', 'accent', 'accent']
const INSIGHT_ICONS: LucideIcon[] = [PersonStanding, Bike, ShieldAlert]

const DEFAULT_FILTERS: DashboardFilters = { timeRange: 'Last 12 months', area: 'All areas', roadUser: 'All road users', severity: 'All severity levels' }
const TIME_RANGES = ['Last 12 months', 'Last 6 months', 'Year to date', 'All time']
const ROAD_USERS = ['All road users', 'Pedestrians', 'Cyclists', 'Drivers']
const SEVERITIES = ['All severity levels', 'Property damage only', 'Injury', 'Serious injury', 'Fatal']

function describeError(err: unknown): string {
  if (err instanceof BackendError && err.status === 429) {
    return 'Too many requests right now. Please wait a moment and try again.'
  }
  return 'Something went wrong loading the dashboard. Please try again in a moment.'
}

interface FilterSelectProps {
  label: string
  value: string
  options: string[]
  onChange: (value: string) => void
}

function FilterSelect({ label, value, options, onChange }: FilterSelectProps) {
  return (
    <label className="flex flex-col gap-1 text-xs text-text-muted">
      {label}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-lg border border-border bg-surface-elevated px-3 py-2 text-sm text-text focus:outline-none"
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  )
}

export function DashboardPage() {
  const navigate = useNavigate()
  const [data, setData] = useState<DashboardResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState<DashboardFilters>(DEFAULT_FILTERS)

  // Filters are real query params the backend applies in SQL - every
  // change here re-fetches, it doesn't just re-slice what's already loaded.
  useEffect(() => {
    let isCurrent = true
    getDashboardOverview(filters).then(
      (result) => {
        if (isCurrent) {
          setError(null)
          setData(result)
        }
      },
      (err) => {
        if (isCurrent) setError(describeError(err))
      },
    )
    return () => {
      isCurrent = false
    }
  }, [filters])

  // hotspots always covers every area regardless of the Area filter (see
  // dashboard_service.py's docstring) - narrowed here client-side for the
  // map, same as before; this is also what keeps the Area dropdown's own
  // option list stable no matter which area is currently selected.
  const areaOptions = useMemo(() => ['All areas', ...(data?.hotspots.map((h) => h.area) ?? [])], [data])
  const visibleHotspots = useMemo(() => {
    if (!data) return []
    if (filters.area === 'All areas') return data.hotspots
    return data.hotspots.filter((h) => h.area === filters.area)
  }, [data, filters.area])

  if (error) {
    return (
      <div className="min-h-screen">
        <PageHeader centerSlot={<TopModeToggle />} />
        <div className="px-4 py-10 md:px-8">
          <Card className="flex items-start gap-3">
            <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-danger/15 text-danger">
              <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            </span>
            <p className="text-sm text-text">{error}</p>
          </Card>
        </div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="min-h-screen">
        <PageHeader centerSlot={<TopModeToggle />} />
        <p className="px-8 py-10 text-sm text-text-muted">Loading dashboard...</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      <PageHeader
        centerSlot={<TopModeToggle />}
        title="Montgomery County Traffic Safety Overview"
        subtitle="Simple, public-friendly insights from county crash data and reports."
      />

      <div className="flex flex-col gap-6 px-4 py-6 md:px-8">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {data.metrics.map((metric, index) => (
            <MetricCard key={metric.label} metric={metric} icon={METRIC_ICONS[index]} tone={METRIC_TONES[index]} />
          ))}
        </div>

        <div className="flex flex-wrap items-end gap-3">
          <FilterSelect label="Time range" value={filters.timeRange} options={TIME_RANGES} onChange={(v) => setFilters((f) => ({ ...f, timeRange: v }))} />
          <FilterSelect label="Area" value={filters.area} options={areaOptions} onChange={(v) => setFilters((f) => ({ ...f, area: v }))} />
          <FilterSelect label="Road user" value={filters.roadUser} options={ROAD_USERS} onChange={(v) => setFilters((f) => ({ ...f, roadUser: v }))} />
          <FilterSelect label="Severity" value={filters.severity} options={SEVERITIES} onChange={(v) => setFilters((f) => ({ ...f, severity: v }))} />
          <button
            type="button"
            onClick={() => setFilters(DEFAULT_FILTERS)}
            className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm text-text-muted transition-colors hover:bg-surface-elevated hover:text-text"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            Reset filters
          </button>
        </div>

        <div className="grid gap-5 lg:grid-cols-3">
          <Card>
            <div className="flex items-center gap-1.5">
              <h3 className="text-sm font-semibold">Crashes over time</h3>
              <InfoTooltip label="Total crashes reported each period, across all road users." />
            </div>
            <div className="mt-2">
              <CrashTrendChart data={data.crashTrend} description="Line chart of total crashes by month." />
            </div>
          </Card>

          <Card>
            <div className="flex items-center gap-1.5">
              <h3 className="text-sm font-semibold">Crashes by severity</h3>
              <InfoTooltip label="How many crashes fell into each severity category." />
            </div>
            <div className="mt-2">
              <SeverityBarChart data={data.severityBreakdown} description="Bar chart of crashes by severity category." />
            </div>
          </Card>

          <Card>
            <div className="flex items-center gap-1.5">
              <h3 className="text-sm font-semibold">Who is affected most?</h3>
              <InfoTooltip label="Share of crashes by the type of road user involved." />
            </div>
            <div className="mt-2">
              <RoadUserDonutChart
                data={data.roadUserBreakdown}
                centerValue={data.metrics[0].value}
                centerLabel="TOTAL"
                description="Donut chart of crashes by road user type."
              />
              <ul className="mt-3 flex flex-col gap-1.5 text-xs">
                {data.roadUserBreakdown.map((entry) => (
                  <li key={entry.label} className="flex items-center justify-between gap-2 text-text-muted">
                    <span className="flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full" style={{ background: entry.color }} aria-hidden="true" />
                      {entry.label}
                    </span>
                    <span className="font-medium text-text">{entry.value}%</span>
                  </li>
                ))}
              </ul>
            </div>
          </Card>
        </div>

        <div className="grid gap-5 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <div className="flex items-center gap-1.5">
              <h3 className="text-sm font-semibold">Crash hotspots by area</h3>
              <InfoTooltip label="Brighter, larger markers show where more crashes are reported." />
            </div>
            <div className="mt-2">
              <CrashHotspotMap
                hotspots={visibleHotspots}
                referenceLocations={mockReferenceLocations}
                onSelectHotspot={() => navigate('/dashboard/hotspots')}
              />
            </div>
          </Card>

          <Card>
            <h3 className="text-sm font-semibold">What stands out</h3>
            <ul className="mt-3 flex flex-col gap-3">
              {data.insights.map((insight, index) => {
                const Icon = INSIGHT_ICONS[index] ?? ShieldAlert
                return (
                  <li key={insight.id} className="flex items-start gap-2.5 text-sm text-text-muted">
                    <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent/15 text-accent">
                      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                    </span>
                    {insight.text}
                  </li>
                )
              })}
            </ul>
          </Card>
        </div>

        {data.dataAsOf && (
          <p className="text-xs text-text-muted">Updated from county datasets and public safety reports as of {formatDate(data.dataAsOf)}.</p>
        )}
      </div>
    </div>
  )
}
