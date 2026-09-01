/** Formats an ISO timestamp (e.g. from a backend's dataAsOf field) as a
 * plain-language date - "Aug 31, 2026" not a raw ISO string, per the
 * project's public-friendly-language rule. Falls back to the raw input if
 * it isn't a parseable date, so a malformed value degrades instead of
 * crashing the page.
 */
export function formatDate(isoString: string | undefined | null): string {
  if (!isoString) return 'an unknown date'
  const date = new Date(isoString)
  if (Number.isNaN(date.getTime())) return isoString
  return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
}
