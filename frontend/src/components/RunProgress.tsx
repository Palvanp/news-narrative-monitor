import type { Run } from '../api/client'

const STAGE_NAMES: Record<string, string> = {
  collect: 'Collecting coverage from news feeds',
  fetch_bodies: 'Fetching article text',
  clean: 'Cleaning and detecting language',
  store: 'Storing articles',
  embed: 'Computing multilingual embeddings',
  sentiment: 'Classifying sentiment',
  entities: 'Extracting entities',
  cluster: 'Clustering into narratives',
  evidence: 'Selecting evidence',
  naming: 'Naming narratives',
  done: 'Done',
}

export default function RunProgress({ run }: { run: Run }) {
  if (run.status === 'failed') {
    return (
      <div className="panel">
        <h2 className="error">Run failed</h2>
        <p>{run.error}</p>
      </div>
    )
  }
  const title = run.status === 'pending' ? 'Waiting to start…' : (STAGE_NAMES[run.stage ?? ''] ?? run.stage)
  return (
    <div className="panel stack">
      <div className="spread">
        <h2>{title}</h2>
        <span className="tabular secondary">{Math.round(run.progress * 100)}%</span>
      </div>
      <div className="progress">
        <div style={{ width: `${run.progress * 100}%` }} />
      </div>
      {run.message && <p className="muted small">{run.message}</p>}
      <p className="muted small">
        A run usually takes under a minute. The first run after the server starts also loads the language models,
        and naming narratives waits on the LLM when it is connected.
      </p>
    </div>
  )
}
