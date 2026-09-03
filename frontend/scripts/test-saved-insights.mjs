import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'

const server = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

try {
  const storageModule = await server.ssrLoadModule('/src/lib/savedInsights.ts')
  const { SIDEBAR_NAV_ITEMS } = await server.ssrLoadModule('/src/constants/navigation.ts')
  const { AppRoutes } = await server.ssrLoadModule('/src/app/routes.tsx')
  const memory = new Map()
  const storage = {
    getItem: (key) => memory.get(key) ?? null,
    setItem: (key, value) => memory.set(key, value),
  }

  const makeResponse = (id, question = `Traffic-safety question ${id}?`) => ({
    id,
    question,
    answer: `Answer for ${id}`,
    summary: `Summary for ${id}`,
    metrics: [],
    crashTrend: [],
    hotspots: [],
    whatDataMeans: 'Meaning',
    countyReportPoints: [],
    visualizations: [{ id: `viz-${id}`, type: 'bar', title: `Chart ${id}`, data: { points: [{ x: 'A', y: 1 }] } }],
    citations: [],
    followUpPrompts: [],
  })

  assert.equal(SIDEBAR_NAV_ITEMS.find((item) => item.label === 'Saved insights')?.path, '/saved-insights')
  assert.deepEqual(storageModule.listSavedInsights(storage), [])

  const saved = storageModule.saveInsight(makeResponse('query-1', 'How many pedestrian crashes occurred?'), storage)
  assert.equal(saved?.id, 'query-1')
  assert.equal(storageModule.getSavedInsight('query-1', storage)?.response.visualizations[0].title, 'Chart query-1')
  assert.equal(storageModule.isInsightSaved('query-1', storage), true)

  storageModule.saveInsight(makeResponse('query-1', 'Updated crash question?'), storage)
  assert.equal(storageModule.listSavedInsights(storage).length, 1, 'saving the same response twice must not duplicate it')
  assert.equal(storageModule.getSavedInsight('query-1', storage)?.response.question, 'Updated crash question?')

  storageModule.removeSavedInsight('query-1', storage)
  assert.deepEqual(storageModule.listSavedInsights(storage), [])

  for (let index = 0; index < 30; index += 1) {
    storageModule.saveInsight(makeResponse(`query-${index}`), storage)
  }
  const capped = storageModule.listSavedInsights(storage)
  assert.equal(capped.length, 25)
  assert.equal(capped[0].id, 'query-29')

  const renderRoute = (path) => renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries: [path] },
      React.createElement(AppRoutes),
    ),
  )

  const indexHtml = renderRoute('/saved-insights')
  assert.match(indexHtml, /Saved insights/)
  assert.match(indexHtml, /No saved insights yet/)

  const formerMockHtml = renderRoute('/saved-insights/silver-spring-pedestrian-safety')
  assert.match(formerMockHtml, /Saved insight not found/)
  assert.doesNotMatch(formerMockHtml, /Silver Spring Pedestrian Safety Snapshot/)

  globalThis.window = { localStorage: storage }
  const populatedIndexHtml = renderRoute('/saved-insights')
  assert.match(populatedIndexHtml, /Traffic-safety question query-29/)
  assert.match(populatedIndexHtml, /href="\/saved-insights\/query-29"/)

  const savedDetailHtml = renderRoute('/saved-insights/query-29')
  assert.match(savedDetailHtml, /Answer for query-29/)
  assert.match(savedDetailHtml, /Chart query-29/)
  assert.doesNotMatch(savedDetailHtml, /Silver Spring Pedestrian Safety Snapshot/)
  delete globalThis.window

  console.log('Saved Insights storage and route regression tests passed.')
} finally {
  await server.close()
}
