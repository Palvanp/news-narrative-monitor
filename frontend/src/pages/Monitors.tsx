import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, LANGUAGE_NAMES, type Monitor } from '../api/client'
import { shortTime } from '../components/format'

function windowLabel(hours: number): string {
  return hours % 24 === 0 ? `${hours / 24} day${hours === 24 ? '' : 's'}` : `${hours}h`
}

export default function Monitors() {
  const monitors = useQuery({ queryKey: ['monitors'], queryFn: () => api<Monitor[]>('/monitors') })
  const list = monitors.data ?? []
  const completed = list.filter((m) => m.latest_run?.status === 'completed').length

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <div className="eyebrow">Your workspace</div>
          <h1>Monitors</h1>
        </div>
        <Link to="/" className="button">
          New monitor
        </Link>
      </div>

      <div className="bento">
        <div className="card accent span-4">
          <span className="small">Monitors</span>
          <span className="big-num">{list.length}</span>
        </div>
        <div className="card span-4">
          <span className="small secondary">Completed analyses</span>
          <span className="big-num">{completed}</span>
        </div>
        <div className="card span-4">
          <span className="small secondary">Latest</span>
          <span className="serif" style={{ fontSize: '1.5rem', lineHeight: 1.1 }}>
            {list[0]?.topic ?? 'None yet'}
          </span>
        </div>

        <div className="card span-12">
          {monitors.isLoading && <p className="muted">Loading…</p>}
          {monitors.error && <p className="error">{monitors.error.message}</p>}
          {monitors.data?.length === 0 && (
            <div className="empty">
              <h2>No monitors yet</h2>
              <p>Pick a story on the Discover page to start your first analysis.</p>
            </div>
          )}
          {!!list.length && (
            <div className="table-scroll">
              <table className="data">
                <thead>
                  <tr>
                    <th>Topic</th>
                    <th>Window</th>
                    <th>Languages</th>
                    <th>Status</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((m) => (
                    <tr key={m.id}>
                      <td>
                        <Link to={`/monitors/${m.id}`}>{m.topic}</Link>
                      </td>
                      <td>{windowLabel(m.time_range_hours)}</td>
                      <td>{m.languages.map((l) => LANGUAGE_NAMES[l] ?? l).join(' + ')}</td>
                      <td>
                        <span className={`status-tag ${m.latest_run?.status ?? ''}`}>{m.latest_run?.status ?? 'not run'}</span>
                      </td>
                      <td className="muted">{shortTime(m.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
