import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, type Monitor, type Trending, type TrendingTopic } from '../api/client'
import { shortTime } from '../components/format'

function TrendingTopics({ onPick }: { onPick: (t: TrendingTopic, hours: number) => void }) {
  const trending = useQuery({
    queryKey: ['trending'],
    queryFn: () => api<Trending>('/trending'),
    staleTime: 10 * 60 * 1000,
  })
  const data = trending.data
  return (
    <div className="panel stack">
      <div className="spread">
        <h2>In the news now</h2>
        {data && <span className="muted small">English + Hindi coverage, last {Math.round(data.window_hours / 24)} days</span>}
      </div>
      {trending.isLoading && <p className="muted small">Reading today's headlines from the news feeds…</p>}
      {trending.error && <p className="muted small">Couldn't load trending topics: {trending.error.message}</p>}
      {data && data.topics.length === 0 && (
        <p className="muted small">
          {data.error ? `Couldn't read the feeds (${data.error}).` : 'No story has enough English and Hindi coverage right now.'}
        </p>
      )}
      {!!data?.topics.length && (
        <div className="trends">
          {data.topics.map((t) => (
            <button type="button" className="trend" key={t.topic} onClick={() => onPick(t, data.window_hours)}>
              <span className="trend-topic">{t.topic}</span>
              <span className="split" aria-hidden>
                <span style={{ flex: t.en, background: 'var(--lang-en)' }} />
                <span style={{ flex: t.hi, background: 'var(--lang-hi)' }} />
              </span>
              <span className="small secondary tabular">
                {t.en + t.hi} articles · {t.en} English · {t.hi} Hindi
              </span>
              {t.headlines[0] && <span className="small muted trend-headline">“{t.headlines[0]}”</span>}
            </button>
          ))}
        </div>
      )}
      <p className="muted small">Pick a story to fill in the form. A topic needs roughly 25+ articles for narratives to form.</p>
    </div>
  )
}

const RANGES = [
  { hours: 6, label: 'Last 6 hours' },
  { hours: 24, label: 'Last 24 hours' },
  { hours: 72, label: 'Last 3 days' },
  { hours: 168, label: 'Last 7 days' },
]

export default function Home() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [topic, setTopic] = useState('')
  const [hindiKeywords, setHindiKeywords] = useState('')
  const [hours, setHours] = useState(24)
  const [languages, setLanguages] = useState<string[]>(['en', 'hi'])

  const monitors = useQuery({ queryKey: ['monitors'], queryFn: () => api<Monitor[]>('/monitors') })
  const create = useMutation({
    mutationFn: () =>
      api<Monitor>('/monitors', {
        method: 'POST',
        body: JSON.stringify({ topic, hindi_keywords: hindiKeywords || null, languages, time_range_hours: hours }),
      }),
    onSuccess: (monitor) => {
      queryClient.invalidateQueries({ queryKey: ['monitors'] })
      navigate(`/monitors/${monitor.id}`)
    },
  })

  const topicInput = useRef<HTMLInputElement>(null)
  const pick = (t: TrendingTopic, windowHours: number) => {
    setTopic(t.topic)
    setHours(windowHours)
    setLanguages(['en', 'hi'])
    setHindiKeywords('')
    topicInput.current?.focus()
    topicInput.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
  const toggle = (lang: string) =>
    setLanguages((cur) => (cur.includes(lang) ? cur.filter((l) => l !== lang) : [...cur, lang]))

  const submit = (e: FormEvent) => {
    e.preventDefault()
    create.mutate()
  }

  return (
    <div className="stack">
      <TrendingTopics onPick={pick} />
      <form className="panel stack" onSubmit={submit}>
        <h2>Create a monitor</h2>
        <div className="form-grid">
          <label>
            Topic / event
            <input
              ref={topicInput}
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="Pick a story above, or type one in the news this week"
              required
              minLength={3}
            />
          </label>
          <label>
            Time range
            <select value={hours} onChange={(e) => setHours(Number(e.target.value))}>
              {RANGES.map((r) => (
                <option key={r.hours} value={r.hours}>
                  {r.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>
              Hindi keywords <span className="muted">(optional, e.g. भारत अमेरिका व्यापार)</span>
            </span>
            <input type="text" value={hindiKeywords} onChange={(e) => setHindiKeywords(e.target.value)} />
          </label>
          <div>
            <div className="small secondary" style={{ marginBottom: 6 }}>
              Languages
            </div>
            <div className="checks">
              <label>
                <input type="checkbox" checked={languages.includes('en')} onChange={() => toggle('en')} /> English
              </label>
              <label>
                <input type="checkbox" checked={languages.includes('hi')} onChange={() => toggle('hi')} /> Hindi
              </label>
            </div>
          </div>
        </div>
        <div className="row">
          <button type="submit" disabled={create.isPending || !languages.length}>
            {create.isPending ? 'Starting…' : 'Start monitoring'}
          </button>
          {create.error && <span className="error small">{create.error.message}</span>}
        </div>
      </form>

      <div className="panel">
        <h2>Monitors</h2>
        {monitors.isLoading && <p className="muted">Loading…</p>}
        {monitors.data?.length === 0 && <p className="muted">No monitors yet.</p>}
        {!!monitors.data?.length && (
          <div className="table-scroll">
            <table className="data" style={{ marginTop: 8 }}>
              <thead>
                <tr>
                  <th>Topic</th>
                  <th>Window</th>
                  <th>Languages</th>
                  <th>Last run</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {monitors.data.map((m) => (
                  <tr key={m.id}>
                    <td>
                      <Link to={`/monitors/${m.id}`}>{m.topic}</Link>
                    </td>
                    <td>{m.time_range_hours}h</td>
                    <td>{m.languages.join(', ')}</td>
                    <td>{m.latest_run?.status ?? 'none'}</td>
                    <td className="muted">{shortTime(m.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
