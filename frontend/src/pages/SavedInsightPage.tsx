import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Bookmark, Download, MessageCirclePlus, Share2, Sparkles } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { Card } from '@/components/common/Card'
import { MetricCard } from '@/components/common/MetricCard'
import { PromptChip } from '@/components/common/PromptChip'
import { SourceChip } from '@/components/common/SourceChip'
import { EmptyState } from '@/components/common/EmptyState'
import { CrashTrendChart } from '@/components/charts/CrashTrendChart'
import { CorridorBarChart } from '@/components/charts/CorridorBarChart'
import { getSavedInsight } from '@/services/queryService'
import type { SavedInsight } from '@/types/insight'
import { buildAskResultPath } from '@/lib/askRoute'

export function SavedInsightPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [insight, setInsight] = useState<SavedInsight | null | undefined>(undefined)
  const [shareStatus, setShareStatus] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    getSavedInsight(id).then((result) => setInsight(result ?? null))
  }, [id])

  async function handleShare() {
    const url = window.location.href
    try {
      if (navigator.share) {
        await navigator.share({ title: insight?.title, url })
        setShareStatus('Shared.')
      } else {
        await navigator.clipboard.writeText(url)
        setShareStatus('Link copied to clipboard.')
      }
    } catch {
      setShareStatus('Could not share this link.')
    }
    setTimeout(() => setShareStatus(null), 3000)
  }

  if (insight === undefined) {
    return <p className="px-8 py-10 text-sm text-text-muted">Loading saved insight...</p>
  }

  if (insight === null) {
    return (
      <div className="px-4 py-10 md:px-8">
        <EmptyState icon={Bookmark} title="Saved insight not found" description="This saved insight may have been removed, or the link is incorrect." />
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      <PageHeader
        leadingSlot={
          <Link to="/dashboard" className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs text-text-muted hover:text-text">
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
            Saved insight
          </Link>
        }
        title={insight.title}
        subtitle={`Generated ${formatDate(insight.generatedAt)} · Public summary`}
        actions={
          <>
            <button
              type="button"
              onClick={handleShare}
              className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm text-text-muted transition-colors hover:bg-surface-elevated hover:text-text"
            >
              <Share2 className="h-3.5 w-3.5" aria-hidden="true" />
              Share
            </button>
            <button
              type="button"
              disabled
              title="PDF export is coming soon"
              className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm text-text-muted opacity-50"
            >
              <Download className="h-3.5 w-3.5" aria-hidden="true" />
              Download PDF
            </button>
            <button
              type="button"
              onClick={() => navigate('/ask')}
              className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-black transition-colors hover:bg-accent-dark"
            >
              <MessageCirclePlus className="h-3.5 w-3.5" aria-hidden="true" />
              Ask a follow-up
            </button>
          </>
        }
      />

      <div className="flex flex-col gap-6 px-4 py-6 md:px-8">
        {shareStatus && (
          <p role="status" className="text-sm text-accent">
            {shareStatus}
          </p>
        )}

        <Card className="flex items-start gap-3">
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent/15 text-accent">
            <Sparkles className="h-4 w-4" aria-hidden="true" />
          </span>
          <p className="text-sm text-text md:text-base">{insight.summary}</p>
        </Card>

        <div className="grid gap-4 sm:grid-cols-3">
          {insight.metrics.map((metric) => (
            <MetricCard key={metric.label} metric={metric} />
          ))}
        </div>

        <div className="grid gap-5 lg:grid-cols-2">
          <Card>
            <h3 className="text-sm font-semibold text-text-muted">Pedestrian crashes over time</h3>
            <div className="mt-2">
              <CrashTrendChart data={insight.crashTrend} description={insight.summary} />
            </div>
          </Card>
          <Card>
            <h3 className="text-sm font-semibold text-text-muted">Most affected corridors (2022-2024)</h3>
            <div className="mt-2">
              <CorridorBarChart data={insight.corridors} description="Horizontal bar chart of crashes by corridor." />
            </div>
          </Card>
        </div>

        <div className="grid gap-5 lg:grid-cols-2">
          <Card>
            <h3 className="text-sm font-semibold">What MoCoLens found</h3>
            <ul className="mt-3 flex flex-col gap-2 text-sm text-text-muted">
              {insight.findings.map((finding) => (
                <li key={finding} className="flex items-start gap-2">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-positive" aria-hidden="true" />
                  {finding}
                </li>
              ))}
            </ul>
          </Card>
          <Card>
            <h3 className="text-sm font-semibold">Questions you might ask next</h3>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {insight.followUpPrompts.map((prompt) => (
                <PromptChip key={prompt} label={prompt} onClick={() => navigate(buildAskResultPath(prompt))} />
              ))}
            </div>
          </Card>
        </div>

        <div>
          <h3 className="mb-2 text-sm font-semibold text-text-muted">Sources</h3>
          <div className="flex flex-wrap gap-2">
            {insight.citations.map((citation) => (
              <SourceChip key={citation.id} citation={citation} />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
}
