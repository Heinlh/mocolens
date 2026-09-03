import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Bookmark, ChevronRight, MessageCirclePlus, Trash2 } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { TopModeToggle } from '@/components/layout/TopModeToggle'
import { Card } from '@/components/common/Card'
import { EmptyState } from '@/components/common/EmptyState'
import { listSavedInsights, removeSavedInsight } from '@/lib/savedInsights'

export function SavedInsightsPage() {
  const [insights, setInsights] = useState(listSavedInsights)

  function handleRemove(id: string) {
    removeSavedInsight(id)
    setInsights(listSavedInsights())
  }

  return (
    <div className="min-h-screen">
      <PageHeader
        centerSlot={<TopModeToggle />}
        title="Saved insights"
        subtitle="Answers you saved in this browser, with their original evidence and visualizations."
      />

      <div className="flex flex-col gap-5 px-4 py-6 md:px-8">
        {insights.length === 0 ? (
          <div className="flex flex-col items-center gap-4">
            <div className="w-full">
              <EmptyState
                icon={Bookmark}
                title="No saved insights yet"
                description="Ask a traffic-safety question, then choose Save on the answer to keep it here."
              />
            </div>
            <Link
              to="/ask"
              className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-black transition-colors hover:bg-accent-dark"
            >
              <MessageCirclePlus className="h-4 w-4" aria-hidden="true" />
              Ask a question
            </Link>
          </div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {insights.map((insight) => (
              <Card key={insight.id} className="flex items-start gap-3">
                <Link to={`/saved-insights/${encodeURIComponent(insight.id)}`} className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-accent">Saved {formatDate(insight.savedAt)}</p>
                  <h2 className="mt-1 text-base font-semibold text-text">{insight.response.question}</h2>
                  <p className="mt-2 line-clamp-3 text-sm text-text-muted">{insight.response.summary || insight.response.answer}</p>
                  <span className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-accent">
                    Open insight
                    <ChevronRight className="h-4 w-4" aria-hidden="true" />
                  </span>
                </Link>
                <button
                  type="button"
                  onClick={() => handleRemove(insight.id)}
                  aria-label={`Remove saved insight: ${insight.response.question}`}
                  className="rounded-lg p-2 text-text-muted transition-colors hover:bg-danger/10 hover:text-danger"
                >
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                </button>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}
