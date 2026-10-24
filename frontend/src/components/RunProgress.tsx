import type { Run } from '../api/client'

const STAGES: [string, string][] = [
  ['collect', 'Collecting coverage from news feeds'],
  ['fetch_bodies', 'Fetching article text'],
  ['clean', 'Cleaning and detecting language'],
  ['store', 'Storing articles'],
  ['embed', 'Computing multilingual embeddings'],
  ['sentiment', 'Classifying sentiment'],
  ['entities', 'Extracting entities'],
  ['cluster', 'Clustering into narratives'],
  ['evidence', 'Selecting evidence'],
  ['naming', 'Naming narratives'],
]

export default function RunProgress({ run }: { run: Run }) {
  if (run.status === 'failed') {
    return (
      <div className="card">
        <h2 className="error">Run failed</h2>
        <p style={{ margin: 0 }}>{run.error}</p>
      </div>
    )
  }
  const current = STAGES.findIndex(([key]) => key === run.stage)
  const title = run.status === 'pending' ? 'Waiting to start…' : (STAGES[current]?.[1] ?? run.stage)
  return (
    <div className="card">
      <div className="spread">
        <div>
          <div className="eyebrow">Analysis running</div>
          <h2 className="serif" style={{ fontSize: '1.8rem' }}>
            {title}
          </h2>
        </div>
        <span className="big-num" style={{ color: 'var(--red)' }}>
          {Math.round(run.progress * 100)}%
        </span>
      </div>
      <div className="progress">
        <div style={{ width: `${run.progress * 100}%` }} />
      </div>
      {run.message && <p className="muted small" style={{ margin: 0 }}>{run.message}</p>}
      <ol className="steps">
        {STAGES.map(([key, label], i) => (
          <li key={key} className={i < current ? 'done' : i === current ? 'current' : ''}>
            {label}
          </li>
        ))}
      </ol>
      <p className="muted tiny" style={{ margin: 0 }}>
        A run usually takes under a minute. The first run after the server starts also loads the language models, and
        naming narratives waits on the LLM when it is connected.
      </p>
    </div>
  )
}
