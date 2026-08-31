import { Car, FileText, Footprints, Users } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { DataSource } from '@/types/sources'
import { Card } from '@/components/common/Card'
import { Badge } from '@/components/common/Badge'

const ICONS: Record<DataSource['icon'], LucideIcon> = { car: Car, users: Users, footprints: Footprints, fileText: FileText }

interface DataSourceCardProps {
  source: DataSource
}

export function DataSourceCard({ source }: DataSourceCardProps) {
  const Icon = ICONS[source.icon]

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-accent/15 text-accent">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </span>
        <Badge variant={source.type === 'dataset' ? 'accent' : 'neutral'}>{source.type === 'dataset' ? 'Dataset' : 'Report'}</Badge>
      </div>
      <div>
        <p className="font-semibold text-text">{source.title}</p>
        <p className="mt-1 text-sm text-text-muted">{source.description}</p>
      </div>
      <div className="mt-auto flex flex-wrap items-center gap-2 pt-2 text-xs text-text-muted">
        <span className="rounded-full border border-border px-2 py-1">{source.refreshCadence}</span>
        <span>Updated {formatDate(source.lastUpdated)}</span>
      </div>
    </Card>
  )
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}
