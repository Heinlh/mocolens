/** Shared fetch helper for both services, so "backend unreachable" and
 * "backend reachable but rejected the request" are told apart consistently
 * everywhere instead of both silently becoming mock data. A rate limit or a
 * real server error is a fact worth showing the user - substituting mock
 * data for it would make the app lie about why nothing changed.
 */

export class BackendError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'BackendError'
    this.status = status
  }
}

export function isBackendConfigured(): boolean {
  return Boolean(import.meta.env.VITE_API_BASE_URL)
}

/** Throws BackendError for a reachable-but-rejected response (4xx/5xx) -
 * callers should show this to the user. Throws a plain Error/TypeError for
 * an unreachable backend (network failure, CORS, DNS) - callers should fall
 * back to mock data, since that's the standalone-demo case.
 */
export async function backendFetch(path: string, init?: RequestInit): Promise<Response> {
  const base = import.meta.env.VITE_API_BASE_URL as string
  const res = await fetch(`${base}${path}`, init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      // response wasn't JSON - keep statusText
    }
    throw new BackendError(res.status, detail)
  }
  return res
}
