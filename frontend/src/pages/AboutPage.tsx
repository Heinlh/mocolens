import { PageHeader } from '@/components/layout/PageHeader'
import { TopModeToggle } from '@/components/layout/TopModeToggle'
import { Card } from '@/components/common/Card'

export function AboutPage() {
  return (
    <div className="min-h-screen">
      <PageHeader centerSlot={<TopModeToggle />} title="About MoCoLens" subtitle="See it. Understand it. Save lives." />
      <div className="flex flex-col gap-4 px-4 py-6 md:px-8">
        <Card className="max-w-2xl text-sm text-text-muted">
          <p>
            MoCoLens helps the public ask plain-English questions about Montgomery County traffic safety and get
            answers grounded in public crash data and county reports, with sources always shown.
          </p>
          <p className="mt-3">
            This is a prototype under active development. Data shown throughout the application is mocked while the
            data ingestion, analytics, and agentic retrieval backend is being built.
          </p>
        </Card>
      </div>
    </div>
  )
}
