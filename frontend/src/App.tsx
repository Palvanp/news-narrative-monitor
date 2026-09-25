import { useQuery } from '@tanstack/react-query'
import { Link, Route, Routes } from 'react-router-dom'
import { api, type Health } from './api/client'
import BriefView from './pages/BriefView'
import Dashboard from './pages/Dashboard'
import Home from './pages/Home'
import NarrativeView from './pages/NarrativeView'

function StatusBar() {
  const { data, error } = useQuery({
    queryKey: ['health'],
    queryFn: () => api<Health>('/health'),
    refetchInterval: 15000,
  })
  if (error) {
    return (
      <div className="status">
        <span>
          <i className="dot bad" />
          Backend unreachable
        </span>
      </div>
    )
  }
  if (!data) return <div className="status">Checking backend…</div>
  return (
    <div className="status">
      <span>
        <i className={`dot ${data.db.ok ? 'ok' : 'bad'}`} />
        Database {data.db.ok ? data.db.dialect : 'down'}
      </span>
      <span title={data.llm.hint}>
        <i className={`dot ${data.llm.ok ? 'ok' : 'bad'}`} />
        LLM {data.llm.ok ? 'connected' : 'offline'}
      </span>
    </div>
  )
}

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          Nazar<small>narrative intelligence · English + Hindi</small>
        </Link>
        <StatusBar />
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/monitors/:id" element={<Dashboard />} />
          <Route path="/monitors/:id/brief" element={<BriefView />} />
          <Route path="/narratives/:id" element={<NarrativeView />} />
        </Routes>
      </main>
    </div>
  )
}
