import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, type Monitor, type Trending, type TrendingTopic } from '../api/client'
import { Arrow } from '../components/Bits'
import EyeField from '../components/EyeField'
import { shortTime } from '../components/format'

function TrendingTopics({ onPick }: { onPick: (t: TrendingTopic, hours: number) => void }) {
  const trending = useQuery({
    queryKey: ['trending'],
    queryFn: () => api<Trending>('/trending'),
    staleTime: 10 * 60 * 1000,
  })
  const data = trending.data
  return (
    <section>
      <div className="section-title">
        <h2>In the news now</h2>
        <span className="muted small">
          {data ? `Stories with English and Hindi coverage, last ${Math.round(data.window_hours / 24)} days` : 'Reading today’s headlines…'}
        </span>
      </div>
      {trending.isLoading && (
        <div className="trends" aria-busy="true">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton" />
          ))}
        </div>
      )}
      {trending.error && <p className="muted small">Couldn't load trending topics: {trending.error.message}</p>}
      {data && data.topics.length === 0 && (
        <div className="card soft empty">
          <p>{data.error ? `Couldn't read the feeds (${data.error}).` : 'No story has enough English and Hindi coverage right now.'}</p>
        </div>
      )}
      {!!data?.topics.length && (
        <div className={`trends n${data.topics.length}`}>
          {data.topics.map((t, i) => (
            <button type="button" className="trend" key={t.topic} onClick={() => onPick(t, data.window_hours)}>
              <span className="spread" style={{ alignItems: 'flex-start', flexWrap: 'nowrap' }}>
                <span className="trend-topic">{t.topic}</span>
                <span className="icon-circle">
                  <Arrow />
                </span>
              </span>
              <span>
                <span className="mid-num">{t.en + t.hi}</span> <span className="small secondary">articles</span>
              </span>
              <span>
                <span className="split" aria-hidden>
                  <span style={{ flex: t.en, background: 'var(--lang-en)' }} />
                  <span style={{ flex: t.hi, background: 'var(--lang-hi)' }} />
                </span>
                <span className="tiny secondary tabular" style={{ display: 'block', marginTop: 6 }}>
                  {t.en} English · {t.hi} Hindi
                </span>
              </span>
              {i === 0 && data.topics.length === 5 ? (
                <span className="stack" style={{ gap: 10, marginTop: 'auto' }}>
                  {t.headlines.map((h) => (
                    <span key={h} className="trend-headline muted" style={{ borderTop: '1px solid rgba(255,255,255,0.25)', paddingTop: 10 }}>
                      “{h}”
                    </span>
                  ))}
                </span>
              ) : (
                t.headlines[0] && <span className="muted trend-headline">“{t.headlines[0]}”</span>
              )}
            </button>
          ))}
        </div>
      )}
    </section>
  )
}

const HOW = [
  ['Collect', 'Reads 30 English and Hindi news feeds and keeps the articles that match your topic.'],
  ['Understand', 'Local models embed every article in one shared space, score its sentiment and find the people and organisations named.'],
  ['Cluster', 'Articles telling the same story are grouped into narratives, across both languages.'],
  ['Brief', 'Each narrative is measured, then an LLM writes a brief where every claim cites an article.'],
]

const FACTS = [
  ['30', 'English and Hindi news feeds'],
  ['2', 'languages, clustered together'],
  ['1024-d', 'multilingual embeddings (BGE-M3)'],
  ['~1 min', 'from topic to narratives'],
]

const RANGES = [
  { hours: 6, label: '6h' },
  { hours: 24, label: '24h' },
  { hours: 72, label: '3 days' },
  { hours: 168, label: '7 days' },
]

export default function Home() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [topic, setTopic] = useState('')
  const [hindiKeywords, setHindiKeywords] = useState('')
  const [showHindi, setShowHindi] = useState(false)
  const [hours, setHours] = useState(72)
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
    topicInput.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    topicInput.current?.focus({ preventScroll: true })
  }
  const toggle = (lang: string) =>
    setLanguages((cur) => (cur.includes(lang) ? cur.filter((l) => l !== lang) : [...cur, lang]))

  const submit = (e: FormEvent) => {
    e.preventDefault()
    create.mutate()
  }

  const recent = monitors.data?.slice(0, 4) ?? []

  return (
    <div className="stack-lg">
      <section className="hero">
        <div>
          <div className="hero-kicker">
            English + हिन्दी · Political narrative intelligence
          </div>
          <h1 className="hero-title">
            See the <em>story</em> behind the headlines.
          </h1>
          <p className="hero-lede">
            Pick a topic. Nazar reads English and Hindi news, groups the coverage into the storylines being told, and
            measures how each one grows, spreads and shifts in tone.
          </p>
          <form onSubmit={submit}>
            <div className="ask">
              <input
                ref={topicInput}
                type="text"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="A story in the news this week…"
                aria-label="Topic or event"
                required
                minLength={3}
              />
              <button type="submit" disabled={create.isPending || !languages.length}>
                {create.isPending ? 'Starting…' : 'Start monitoring'}
              </button>
            </div>
            <div className="options">
              <span className="row" style={{ gap: 0 }}>
                <span className="opt-label">Window</span>
                <span className="segmented" role="group" aria-label="Time window">
                  {RANGES.map((r) => (
                    <button type="button" key={r.hours} aria-pressed={hours === r.hours} onClick={() => setHours(r.hours)}>
                      {r.label}
                    </button>
                  ))}
                </span>
              </span>
              <span className="row" style={{ gap: 0 }}>
                <span className="opt-label">Languages</span>
                <span className="segmented" role="group" aria-label="Languages">
                  <button type="button" aria-pressed={languages.includes('en')} onClick={() => toggle('en')}>
                    English
                  </button>
                  <button type="button" aria-pressed={languages.includes('hi')} onClick={() => toggle('hi')}>
                    हिन्दी
                  </button>
                </span>
              </span>
              {!showHindi && (
                <button type="button" className="link-button" onClick={() => setShowHindi(true)}>
                  + Hindi keywords
                </button>
              )}
            </div>
            {showHindi && (
              <label style={{ marginTop: 14, maxWidth: 560 }}>
                <span>
                  Hindi keywords <span className="muted">(optional, e.g. भारत अमेरिका व्यापार)</span>
                </span>
                <input type="text" value={hindiKeywords} onChange={(e) => setHindiKeywords(e.target.value)} lang="hi" />
              </label>
            )}
            {create.error && <p className="error small">{create.error.message}</p>}
          </form>
        </div>

        <figure className="figure">
          <div className="eye-stage">
            <EyeField />
          </div>
        </figure>
      </section>

      <div className="facts">
        {FACTS.map(([value, label]) => (
          <div key={label}>
            <b>{value}</b>
            <span>{label}</span>
          </div>
        ))}
      </div>

      <TrendingTopics onPick={pick} />

      <section>
        <div className="section-title">
          <h2>How it works</h2>
        </div>
        <div className="how">
          {HOW.map(([title, text], i) => (
            <div key={title}>
              <span className="step-n">{String(i + 1).padStart(2, '0')}</span>
              <h3>{title}</h3>
              <p className="small secondary" style={{ margin: 0 }}>
                {text}
              </p>
            </div>
          ))}
        </div>
      </section>

      {recent.length > 0 && (
        <section>
          <div className="section-title">
            <h2>Recent monitors</h2>
            <Link to="/monitors" className="small">
              All monitors →
            </Link>
          </div>
          <div className="bento">
            {recent.map((m) => (
              <Link key={m.id} to={`/monitors/${m.id}`} className="card span-3" style={{ textDecoration: 'none', color: 'inherit' }}>
                <div className="spread" style={{ flexWrap: 'nowrap', alignItems: 'flex-start' }}>
                  <span className="serif" style={{ fontSize: '1.35rem', lineHeight: 1.1 }}>
                    {m.topic}
                  </span>
                  <span className="icon-circle">
                    <Arrow />
                  </span>
                </div>
                <div className="row tiny secondary" style={{ marginTop: 'auto' }}>
                  <span className={`status-tag ${m.latest_run?.status ?? ''}`}>{m.latest_run?.status ?? 'not run'}</span>
                  <span>·</span>
                  <span>{shortTime(m.created_at)}</span>
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
