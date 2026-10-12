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
            Crash figures come from Montgomery County&apos;s open police crash records, and report passages are quoted
            from the county&apos;s Vision Zero publications. Both are checked for updates every week; the Sources page
            lists every dataset and document with the date it was last updated.
          </p>
          <p className="mt-3">
            This is a prototype under active development. Crash counts are not adjusted for how much traffic a road
            carries, so a higher count does not by itself mean a more dangerous road.
          </p>
        </Card>
      </div>
    </div>
  )
}
