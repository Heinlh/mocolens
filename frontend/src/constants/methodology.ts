/** Page copy for the Sources & Methodology screen.
 *
 * Deliberately not served by GET /api/sources: these describe how the
 * product works and what to keep in mind when reading an answer, not the
 * data itself. The endpoint returns only what it can derive from real
 * artifacts (the source registry and the searchable report index), so
 * nothing on that page is prose the backend had to invent.
 *
 * The steps mirror the agent's actual pipeline (src/mocolens/agent/graph.py)
 * and the caveats mirror the analytical-integrity rules the system prompt
 * enforces (src/mocolens/agent/prompts.py).
 */
import type { Caveat, MethodologyStep } from '@/types/sources'

export const METHODOLOGY_STEPS: MethodologyStep[] = [
  { step: 1, title: 'Understand the question.', description: 'We work out what you want to know, and where.' },
  { step: 2, title: 'Check county data.', description: 'We run a checked query against the county crash records.' },
  { step: 3, title: 'Read public reports.', description: 'We search county plans and reports for what they say.' },
  { step: 4, title: 'Explain in plain English.', description: 'We summarize what the evidence shows - and what it does not.' },
]

export const CAVEATS: Caveat[] = [
  { id: 'rates', title: 'Counts are not rates.', description: 'More crashes may reflect more people traveling, not necessarily more danger.' },
  { id: 'reporting', title: 'Not all crashes are reported equally.', description: 'Minor crashes are less likely to be reported, which can affect the totals.' },
  { id: 'causation', title: 'Trends do not prove cause.', description: 'Trends show patterns over time, not why something happened.' },
]
