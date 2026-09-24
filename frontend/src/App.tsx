import { useQuery } from '@tanstack/react-query'
import { Route, Routes } from 'react-router-dom'
import { api, type Health } from './api/client'

function StatusBar() {
  const { data, error } = useQuery({
    queryKey: ['health'],
    queryFn: () => api<Health>('/health'),
    refetchInterval: 15000,
  })
  if (error) return <p className="status bad">Backend unreachable</p>
  if (!data) return <p className="status">Checking backend…</p>
  return (
    <p className="status">
      <span className={data.db.ok ? 'ok' : 'bad'}>DB: {data.db.ok ? data.db.dialect : 'down'}</span>
      {' · '}
      <span className={data.llm.ok ? 'ok' : 'bad'}>
        LLM: {data.llm.ok ? 'connected' : data.llm.hint}
      </span>
    </p>
  )
}

export default function App() {
  return (
    <div className="app">
      <header>
        <h1>Nazar</h1>
        <StatusBar />
      </header>
      <main>
        <Routes>
          <Route path="/" element={<p>Monitor creation comes in milestone 7.</p>} />
        </Routes>
      </main>
    </div>
  )
}
