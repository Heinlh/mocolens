import { ExternalLink } from 'lucide-react'
import type { Citation } from '@/types/sources'

interface CitationTableProps {
  citations: Citation[]
}

export function CitationTable({ citations }: CitationTableProps) {
  return (
    <div className="overflow-x-auto rounded-card border border-border">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-border text-text-muted">
            <th scope="col" className="px-4 py-3 font-medium">
              Document
            </th>
            <th scope="col" className="px-4 py-3 font-medium">
              Date
            </th>
            <th scope="col" className="px-4 py-3 font-medium">
              Pages
            </th>
            <th scope="col" className="w-10 px-4 py-3" />
          </tr>
        </thead>
        <tbody>
          {citations.map((citation) => (
            <tr key={citation.id} className="border-b border-border last:border-0">
              <td className="px-4 py-3 font-medium text-text">{citation.title}</td>
              <td className="px-4 py-3 text-text-muted">{formatPublished(citation.publishedAt)}</td>
              <td className="px-4 py-3 text-text-muted">{citation.page ?? '—'}</td>
              <td className="px-4 py-3 text-right text-text-muted">
                {citation.url ? (
                  <a href={citation.url} target="_blank" rel="noreferrer" className="text-accent hover:text-text">
                    <ExternalLink className="inline h-4 w-4" aria-hidden="true" />
                    <span className="sr-only">Open {citation.title} on the county website</span>
                  </a>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** A bare year stays a year: these documents state a publication year and
 * nothing finer, so rendering "Jan 2025" would invent a month.
 */
function formatPublished(published: string | undefined): string {
  if (!published) return '—'
  if (/^\d{4}$/.test(published)) return published
  const date = new Date(published)
  if (Number.isNaN(date.getTime())) return published
  return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
}
