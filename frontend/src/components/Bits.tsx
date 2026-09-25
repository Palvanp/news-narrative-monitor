import { LANGUAGE_NAMES } from '../api/client'
import { pct } from './format'

export function Growth({ growth, isNew }: { growth: number | null; isNew: boolean }) {
  if (isNew) return <span className="badge new">New this window</span>
  if (growth == null) return <span className="muted small">growth n/a</span>
  const cls = growth > 0 ? 'up' : growth < 0 ? 'down' : ''
  const arrow = growth > 0 ? '↑' : growth < 0 ? '↓' : '→'
  return (
    <span className={`growth ${cls}`} title="Articles in the second half of the window vs the first half">
      {arrow} {growth > 0 ? '+' : ''}
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
