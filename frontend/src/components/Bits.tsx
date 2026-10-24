import { LANGUAGE_NAMES } from '../api/client'
import { pct } from './format'

export function EyeMark({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <path d="M3 16c4-6.5 8.4-9 13-9s9 2.5 13 9c-4 6.5-8.4 9-13 9S7 22.5 3 16z" fill="none" stroke="var(--ink)" strokeWidth="2" strokeLinejoin="round" />
      <circle cx="16" cy="16" r="5.2" fill="none" stroke="var(--ink)" strokeWidth="2" />
      <circle cx="16" cy="16" r="2.6" fill="var(--red)" />
    </svg>
  )
}

export function Arrow({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M4.5 11.5l7-7M5.5 4.5h6v6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function Growth({ growth, isNew }: { growth: number | null; isNew: boolean }) {
  if (isNew) return <span className="badge new">New this window</span>
  if (growth == null) return <span className="muted small">growth n/a</span>
  const cls = growth > 0 ? 'up' : growth < 0 ? 'down' : 'flat'
  const arrow = growth > 0 ? '▲' : growth < 0 ? '▼' : '→'
  return (
    <span className={`growth ${cls}`} title="Articles in the second half of the window vs the first half">
      <span aria-hidden style={{ fontSize: '0.65em' }}>{arrow}</span>
      {growth > 0 ? '+' : ''}
      {growth.toFixed(0)}%
    </span>
  )
}

const SENTIMENTS = [
  { key: 'negative', label: 'Negative', color: 'var(--sent-negative)' },
  { key: 'neutral', label: 'Neutral', color: 'var(--sent-neutral)' },
  { key: 'positive', label: 'Positive', color: 'var(--sent-positive)' },
]

export function SentimentBar({ sentiment }: { sentiment: Record<string, number> }) {
  const parts = SENTIMENTS.filter((s) => (sentiment[s.key] ?? 0) > 0)
  if (!parts.length) return <span className="muted small">No sentiment data</span>
  return (
    <div>
      <div className="split" role="img" aria-label={parts.map((s) => `${s.label} ${pct(sentiment[s.key])}`).join(', ')}>
        {parts.map((s) => (
          <span key={s.key} style={{ width: pct(sentiment[s.key], 1), background: s.color }} />
        ))}
      </div>
      <div className="split-legend">
        {parts.map((s) => (
          <span key={s.key}>
            <i style={{ background: s.color }} />
            {s.label} {pct(sentiment[s.key])}
          </span>
        ))}
      </div>
    </div>
  )
}

export function LanguageSplit({ languages }: { languages: Record<string, number> }) {
  const entries = Object.entries(languages)
  if (!entries.length) return null
  return (
    <div>
      <div className="split" role="img" aria-label={entries.map(([k, v]) => `${LANGUAGE_NAMES[k] ?? k} ${pct(v)}`).join(', ')}>
        {entries.map(([k, v]) => (
          <span key={k} style={{ width: pct(v, 1), background: `var(--lang-${k}, var(--series-other))` }} />
        ))}
      </div>
      <div className="split-legend">
        {entries.map(([k, v]) => (
          <span key={k}>
            <i style={{ background: `var(--lang-${k}, var(--series-other))` }} />
            {LANGUAGE_NAMES[k] ?? k} {pct(v)}
          </span>
        ))}
      </div>
    </div>
  )
}

export function EntityChips({ entities, limit = 6 }: { entities: { id: number; name: string; type: string; articles: number }[]; limit?: number }) {
  if (!entities.length) return <span className="muted small">No entities</span>
  return (
    <div className="chips">
      {entities.slice(0, limit).map((e) => (
        <span className="chip" key={e.id} title={`${e.type} · in ${e.articles} articles`}>
          <b>{e.name}</b> <span className="muted">{e.articles}</span>
        </span>
      ))}
    </div>
  )
}
