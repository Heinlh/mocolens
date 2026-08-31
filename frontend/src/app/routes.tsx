import { Navigate, Route, Routes } from 'react-router-dom'
import { AskHomePage } from '@/pages/AskHomePage'
import { AskResultPage } from '@/pages/AskResultPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { HotspotsPage } from '@/pages/HotspotsPage'
import { SourcesPage } from '@/pages/SourcesPage'
import { SavedInsightPage } from '@/pages/SavedInsightPage'
import { AboutPage } from '@/pages/AboutPage'

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<AskHomePage />} />
      <Route path="/ask" element={<AskHomePage />} />
      <Route path="/ask/result" element={<AskResultPage />} />
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="/dashboard/hotspots" element={<HotspotsPage />} />
      <Route path="/sources" element={<SourcesPage />} />
      <Route path="/saved-insights/:id" element={<SavedInsightPage />} />
      <Route path="/about" element={<AboutPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
