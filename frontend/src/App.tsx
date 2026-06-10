import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppProvider } from './context/AppContext'
import { Layout } from './components/Layout'
import { Dashboard } from './pages/Dashboard'
import { JobMatching } from './pages/JobMatching'
import { MatchResults } from './pages/MatchResults'
import { ResumeIngestion } from './pages/ResumeIngestion'

export default function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="ingestion" element={<ResumeIngestion />} />
            <Route path="matching" element={<JobMatching />} />
            <Route path="results" element={<MatchResults />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AppProvider>
  )
}
