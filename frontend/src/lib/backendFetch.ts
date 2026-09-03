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

export class BackendConfigurationError extends BackendError {
  constructor(message = 'The live data service is not configured for this deployment.') {
    super(503, message)
    this.name = 'BackendConfigurationError'
  }
}

function normalizeBaseUrl(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined
  const normalized = value.trim().replace(/\/+$/, '')
  return normalized || undefined
}

function getBuildTimeBackendBaseUrl(): string | undefined {
  return normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL)
}

let runtimeBaseUrl: string | null | undefined

/** Vercel Functions read environment variables at runtime. This fallback
 * keeps the public API origin out of source control and also works when the
 * Vite build does not receive VITE_API_BASE_URL.
 */
async function getRuntimeBackendBaseUrl(): Promise<string | undefined> {
  if (!import.meta.env.PROD) return undefined
  if (runtimeBaseUrl !== undefined) return runtimeBaseUrl ?? undefined

  try {
    const response = await fetch('/api/config', {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    })
    const body = (await response.json()) as { apiBaseUrl?: unknown }
    runtimeBaseUrl = normalizeBaseUrl(body.apiBaseUrl) ?? null
  } catch {
    runtimeBaseUrl = null
  }

  return runtimeBaseUrl ?? undefined
}

async function resolveBackendUrl(path: string): Promise<string> {
  const baseUrl = getBuildTimeBackendBaseUrl() ?? (await getRuntimeBackendBaseUrl())
  if (!baseUrl) throw new BackendConfigurationError()

  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${baseUrl}${normalizedPath}`
}

/** Throws BackendError for configuration, network, and HTTP failures so
 * production callers never mistake one fixed mock response for live data.
 */
export async function backendFetch(path: string, init?: RequestInit): Promise<Response> {
  let response: Response
  try {
    response = await fetch(await resolveBackendUrl(path), init)
  } catch (err) {
    if (err instanceof BackendError) throw err
    throw new BackendError(0, 'The live data service could not be reached. Please try again shortly.')
  }

  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      // The response was not JSON; retain the HTTP status text.
    }
    throw new BackendError(response.status, detail)
  }

  return response
}
