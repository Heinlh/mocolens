import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Bookmark, MessageCirclePlus, Trash2 } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { EmptyState } from '@/components/common/EmptyState'
import { UserQuestion } from '@/components/chat/UserQuestion'
import { AgentAnswer } from '@/components/chat/AgentAnswer'
import { buildAskResultPath } from '@/lib/askRoute'
import { getSavedInsight, removeSavedInsight } from '@/lib/savedInsights'

export function SavedInsightPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const insight = id ? getSavedInsight(id) : undefined

  function handleDelete() {
    if (!id) return
    removeSavedInsight(id)
    navigate('/saved-insights', { replace: true })
  }

  if (!insight) {
    return (
      <div className="min-h-screen">
        <PageHeader
          leadingSlot={(
            <Link to="/saved-insights" className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs text-text-muted hover:text-text">
              <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
              Saved insights
            </Link>
          )}
        />
        <div className="px-4 py-10 md:px-8">
          <EmptyState icon={Bookmark} title="Saved insight not found" description="This insight is not saved in this browser, or it has been removed." />
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      <PageHeader
        leadingSlot={(
          <Link to="/saved-insights" className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs text-text-muted hover:text-text">
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
            Saved insights
          </Link>
        )}
        title="Saved insight"
        subtitle={`Saved ${formatDate(insight.savedAt)} · Stored in this browser`}
        actions={(
          <>
            <button
              type="button"
              onClick={handleDelete}
              className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm text-text-muted transition-colors hover:border-danger/50 hover:bg-danger/10 hover:text-danger"
            >
              <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
              Remove
            </button>
            <button
              type="button"
              onClick={() => navigate('/ask')}
              className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-black transition-colors hover:bg-accent-dark"
            >
              <MessageCirclePlus className="h-3.5 w-3.5" aria-hidden="true" />
              New question
            </button>
          </>
        )}
      />

      <div className="mx-auto flex max-w-4xl flex-col gap-5 px-4 py-6 md:px-8">
        <UserQuestion question={insight.response.question} askedAt="Saved answer" />
        <AgentAnswer
          response={insight.response}
          onFollowUpClick={(prompt) => navigate(buildAskResultPath(prompt))}
        />
      </div>
    </div>
  )
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
}
