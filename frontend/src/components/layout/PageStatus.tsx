import { AlertTriangle } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { TopModeToggle } from '@/components/layout/TopModeToggle'
import { Card } from '@/components/common/Card'

/** The loading and failure states every backend-driven page shares.
 *
 * A failure is always shown as a failure: no page substitutes prototype
 * data for an unreachable backend, so a visitor is never given a plausible
 * answer that did not come from county data.
 */
export function PageStatus({ message, tone = 'muted' }: { message: string; tone?: 'muted' | 'error' }) {
  return (
    <div className="min-h-screen">
      <PageHeader centerSlot={<TopModeToggle />} />
      {tone === 'error' ? (
        <div className="px-4 py-10 md:px-8">
          <Card className="flex items-start gap-3">
            <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-danger/15 text-danger">
              <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            </span>
            <p className="text-sm text-text">{message}</p>
          </Card>
        </div>
      ) : (
        <p className="px-8 py-10 text-sm text-text-muted">{message}</p>
      )}
    </div>
  )
}
