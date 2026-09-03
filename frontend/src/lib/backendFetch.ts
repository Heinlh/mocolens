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

function getBackendBaseUrl(): string | undefined {
  const configuredUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim()
  return configuredUrl ? configuredUrl.replace(/\/+$/, '') : undefined
}

export function isBackendConfigured(): boolean {
  return Boolean(getBackendBaseUrl())
}

function resolveBackendUrl(path: string): string {
  const baseUrl = getBackendBaseUrl()
  if (!baseUrl) {
    throw new Error('VITE_API_BASE_URL is not configured')
  }

  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${baseUrl}${normalizedPath}`
}

/** Throws BackendError for a reachable-but-rejected response (4xx/5xx) -
 * callers should show this to the user. Throws a plain Error/TypeError for
 * an unreachable backend (network failure, CORS, DNS) - callers should fall
 * back to mock data, since that's the standalone-demo case.
 */
export async function backendFetch(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(resolveBackendUrl(path), init)
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
