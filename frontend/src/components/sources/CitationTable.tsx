import { ChevronRight } from 'lucide-react'
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
              Page
            </th>
            <th scope="col" className="w-10 px-4 py-3" />
          </tr>
        </thead>
        <tbody>
          {citations.map((citation) => (
            <tr key={citation.id} className="border-b border-border last:border-0">
              <td className="px-4 py-3 font-medium text-text">{citation.title}</td>
              <td className="px-4 py-3 text-text-muted">{citation.publishedAt ? formatMonthYear(citation.publishedAt) : '—'}</td>
              <td className="px-4 py-3 text-text-muted">{citation.page ?? '—'}</td>
              <td className="px-4 py-3 text-right text-text-muted">
                <ChevronRight className="inline h-4 w-4" aria-hidden="true" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function formatMonthYear(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
}
