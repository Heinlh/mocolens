export function buildAskResultPath(question: string): string {
  const params = new URLSearchParams({ q: question.trim() })
  return `/ask/result?${params.toString()}`
}
