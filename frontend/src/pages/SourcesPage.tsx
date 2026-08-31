import { useEffect, useState } from 'react'
import { AlertTriangle, Scale, Shield, TrendingUp } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { TopModeToggle } from '@/components/layout/TopModeToggle'
import { Card } from '@/components/common/Card'
import { DataSourceCard } from '@/components/sources/DataSourceCard'
import { CitationTable } from '@/components/sources/CitationTable'
import { getSources } from '@/services/sourceService'
import type { SourcesResponse } from '@/types/sources'

const CAVEAT_ICONS: Record<string, LucideIcon> = { rates: Scale, reporting: AlertTriangle, causation: TrendingUp }

export function SourcesPage() {
  const [data, setData] = useState<SourcesResponse | null>(null)

  useEffect(() => {
    getSources().then(setData)
  }, [])

  if (!data) {
    return (
      <div className="min-h-screen">
        <PageHeader centerSlot={<TopModeToggle />} />
        <p className="px-8 py-10 text-sm text-text-muted">Loading sources...</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      <PageHeader
        centerSlot={<TopModeToggle />}
        title="Sources & methodology"
        subtitle="MoCoLens explains county road safety trends using public datasets and public reports."
        actions={
          <div className="flex items-center gap-2 rounded-card border border-border bg-surface-elevated px-4 py-2.5 text-sm">
            <Shield className="h-4 w-4 text-accent" aria-hidden="true" />
            <span>
              Clear answers, <span className="font-semibold text-accent">grounded in public evidence.</span>
            </span>
          </div>
        }
      />

      <div className="flex flex-col gap-8 px-4 py-6 md:px-8">
        <section>
          <h2 className="mb-3 text-lg font-semibold">Data sources</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {data.sources.map((source) => (
              <DataSourceCard key={source.id} source={source} />
            ))}
          </div>
        </section>

        <section>
          <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold">How MoCoLens answers a question</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {data.methodologySteps.map((step) => (
              <Card key={step.step} className="flex flex-col gap-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent text-sm font-bold text-black">
                  {step.step}
                </span>
                <p className="font-semibold text-text">{step.title}</p>
                <p className="text-sm text-text-muted">{step.description}</p>
              </Card>
            ))}
          </div>
        </section>

        <section>
          <h2 className="mb-3 text-lg font-semibold">What we cite</h2>
          <CitationTable citations={data.citations} />
        </section>

        <section>
          <h2 className="mb-3 text-lg font-semibold">Things to keep in mind</h2>
          <div className="grid gap-4 sm:grid-cols-3">
            {data.caveats.map((caveat) => {
              const Icon = CAVEAT_ICONS[caveat.id] ?? AlertTriangle
              return (
                <Card key={caveat.id} className="flex flex-col gap-2">
                  <Icon className="h-5 w-5 text-accent" aria-hidden="true" />
                  <p className="font-semibold text-text">{caveat.title}</p>
                  <p className="text-sm text-text-muted">{caveat.description}</p>
                </Card>
              )
            })}
          </div>
        </section>
      </div>
    </div>
  )
}
