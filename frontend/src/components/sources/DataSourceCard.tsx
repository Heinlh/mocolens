import { Car, FileText, Footprints, Users } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { DataSource } from '@/types/sources'
import { Card } from '@/components/common/Card'
import { Badge } from '@/components/common/Badge'
import { formatDate } from '@/lib/format'

/** Icon per known registry id, falling back to the source's type. Chosen
 * here rather than sent by the backend: which glyph represents a dataset is
 * a presentation decision, and GET /api/sources should stay a description of
 * the data.
 */
const ICONS_BY_ID: Record<string, LucideIcon> = {
  crash_incidents: Car,
  crash_drivers: Users,
  crash_non_motorists: Footprints,
}

interface DataSourceCardProps {
  source: DataSource
}

export function DataSourceCard({ source }: DataSourceCardProps) {
  const Icon = ICONS_BY_ID[source.id] ?? (source.sourceType === 'dataset' ? Car : FileText)

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-accent/15 text-accent">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </span>
        <Badge variant={source.sourceType === 'dataset' ? 'accent' : 'neutral'}>
          {source.sourceType === 'dataset' ? 'Dataset' : 'Report'}
        </Badge>
      </div>
      <div>
        <p className="font-semibold text-text">{source.title}</p>
        <p className="mt-1 text-sm text-text-muted">{source.description}</p>
      </div>
      <div className="mt-auto flex flex-wrap items-center gap-2 pt-2 text-xs text-text-muted">
        {source.refreshCadence ? (
          <span className="rounded-full border border-border px-2 py-1 capitalize">{source.refreshCadence}</span>
        ) : null}
        {/* No fabricated date when the source has never been ingested. */}
        <span>{source.lastUpdated ? `Updated ${formatDate(source.lastUpdated)}` : 'Not yet ingested'}</span>
      </div>
      {source.url ? (
        <a
          href={source.url}
          target="_blank"
          rel="noreferrer"
          className="text-xs font-medium text-accent underline-offset-2 hover:underline"
        >
          View the county source
        </a>
      ) : null}
    </Card>
  )
}
