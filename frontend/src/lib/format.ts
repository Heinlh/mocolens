/** Formats an ISO timestamp (e.g. from a backend's dataAsOf field) as a
 * plain-language date - "Aug 31, 2026" not a raw ISO string, per the
 * project's public-friendly-language rule. Falls back to the raw input if
 * it isn't a parseable date, so a malformed value degrades instead of
 * crashing the page.
 *
 * A date-only value ("2026-08-30") is rendered in UTC on purpose. JS parses
 * it as UTC midnight, so formatting it in a western local timezone would
 * shift it to the previous day - a snapshot taken on the 30th would be
 * shown to a Maryland reader as the 29th.
 */
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/

export function formatDate(isoString: string | undefined | null): string {
  if (!isoString) return 'an unknown date'
  const date = new Date(isoString)
  if (Number.isNaN(date.getTime())) return isoString
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    ...(DATE_ONLY.test(isoString) ? { timeZone: 'UTC' } : {}),
  })
}
