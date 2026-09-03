function normalizeBaseUrl(value) {
  if (typeof value !== 'string') return null
  const normalized = value.trim().replace(/\/+$/, '')
  return normalized || null
}

export default function handler(request, response) {
  if (request.method !== 'GET') {
    response.setHeader('Allow', 'GET')
    return response.status(405).json({ error: 'Method not allowed' })
  }

  // Prefer a runtime-only variable, while retaining compatibility with the
  // VITE_ name already configured in existing Vercel projects.
  const apiBaseUrl = normalizeBaseUrl(process.env.API_BASE_URL ?? process.env.VITE_API_BASE_URL)

  response.setHeader('Cache-Control', 'no-store')
  return response.status(apiBaseUrl ? 200 : 503).json({ apiBaseUrl })
}
