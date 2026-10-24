import { useQuery } from '@tanstack/react-query'
import { Link, NavLink, Route, Routes } from 'react-router-dom'
import { api, type Health } from './api/client'
import { EyeMark } from './components/Bits'
import BriefView from './pages/BriefView'
import Dashboard from './pages/Dashboard'
import Home from './pages/Home'
import Monitors from './pages/Monitors'
import NarrativeView from './pages/NarrativeView'

const TODAY = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })

function StatusBar() {
  const { data, error } = useQuery({
    queryKey: ['health'],
    queryFn: () => api<Health>('/health'),
    refetchInterval: 15000,
  })
  if (error) {
    return (
      <div className="status">
        <span className="status-pill">
          <i className="dot bad" />
          Backend unreachable
        </span>
      </div>
    )
  }
  if (!data) return <div className="status"><span className="status-pill">Checking backend…</span></div>
  return (
    <div className="status">
      <span className="status-pill" title={data.db.ok ? `Database: ${data.db.dialect}` : 'Database down'}>
        <i className={`dot ${data.db.ok ? 'ok' : 'bad'}`} />
        Database
      </span>
      <span className="status-pill" title={data.llm.hint ?? `${data.llm.naming_model} · ${data.llm.brief_model}`}>
        <i className={`dot ${data.llm.ok ? 'ok' : 'bad'}`} />
        LLM {data.llm.ok ? '' : 'offline'}
      </span>
    </div>
  )
}

export default function App() {
  return (
    <div className="app">
      <header className="masthead">
        <div className="masthead-top">
          <span>{TODAY}</span>
          <span className="row" style={{ gap: 6 }}>
            <EyeMark size={14} /> English &amp; हिन्दी edition
          </span>
          <StatusBar />
        </div>
        <Link to="/" className="masthead-title" aria-label="Nazar home">
          Nazar
        </Link>
        <div className="masthead-sub">Narrative intelligence: every storyline in the news, read in two languages</div>
        <nav className="masthead-bar" aria-label="Main">
          <NavLink to="/" end className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            Discover
          </NavLink>
          <NavLink to="/monitors" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            Monitors
          </NavLink>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/monitors" element={<Monitors />} />
          <Route path="/monitors/:id" element={<Dashboard />} />
          <Route path="/monitors/:id/brief" element={<BriefView />} />
          <Route path="/narratives/:id" element={<NarrativeView />} />
        </Routes>
      </main>
    </div>
  )
}
