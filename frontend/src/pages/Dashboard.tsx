import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { api, LANGUAGE_NAMES, type Monitor, type NarrativeCard, type Run, type Timeline } from '../api/client'
import { EntityChips, Growth, LanguageSplit, SentimentBar } from '../components/Bits'
import { CoverageTimeline } from '../components/Charts'
import RunProgress from '../components/RunProgress'
import { pct, seriesColor, shortTime } from '../components/format'

export default function Dashboard() {
  const id = Number(useParams().id)
  const queryClient = useQueryClient()
  const monitor = useQuery({
    queryKey: ['monitor', id],
    queryFn: () => api<Monitor>(`/monitors/${id}`),
    refetchInterval: (q) => {
      const status = q.state.data?.latest_run?.status
      return status === 'pending' || status === 'running' ? 3000 : false
    },
  })
  const run = monitor.data?.latest_run
  const completed = run?.status === 'completed'
  const narratives = useQuery({
    queryKey: ['narratives', id, run?.id],
    queryFn: () => api<NarrativeCard[]>(`/monitors/${id}/narratives`),
    enabled: completed,
  })
  const timeline = useQuery({
    queryKey: ['timeline', id, run?.id],
    queryFn: () => api<Timeline>(`/monitors/${id}/timeline`),
    enabled: completed,
  })
  const rerun = useMutation({
    mutationFn: () => api<Run>(`/monitors/${id}/run`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['monitor', id] }),
  })

  if (monitor.isLoading) return <p className="muted">Loading…</p>
  if (monitor.error || !monitor.data) return <p className="error">{monitor.error?.message ?? 'Not found'}</p>
  const m = monitor.data
  const stats = run?.stats ?? {}
  const byLang = stats.by_language ?? {}
  const total = Object.values(byLang).reduce((a, b) => a + b, 0)
  const busy = !run || run.status === 'pending' || run.status === 'running'

  return (
    <div className="stack">
      <div className="spread">
        <div>
          <div className="eyebrow">Narrative command center</div>
          <h1>{m.topic}</h1>
          {run?.window_start && (
            <div className="muted small">
              {shortTime(run.window_start)} to {shortTime(run.window_end)} ·{' '}
              {m.languages.map((l) => LANGUAGE_NAMES[l] ?? l).join(' + ')}
            </div>
          )}
        </div>
        <div className="row">
          <button className="ghost" onClick={() => rerun.mutate()} disabled={busy}>
            Run again
          </button>
          {completed && (
            <Link className="button" to={`/monitors/${id}/brief`}>
              Intelligence brief
            </Link>
          )}
        </div>
      </div>

      {run && !completed && <RunProgress run={run} />}

      {completed && (
        <>
          <div className="tiles">
            <div className="tile">
              <div className="value tabular">{total}</div>
              <div className="label">unique relevant items</div>
            </div>
            <div className="tile">
              <div className="value tabular">{stats.unique_sources ?? 'n/a'}</div>
              <div className="label">unique sources</div>
            </div>
            {Object.entries(byLang).map(([lang, n]) => (
              <div className="tile" key={lang}>
                <div className="value tabular">{pct(total ? n / total : 0)}</div>
                <div className="label">
                  {LANGUAGE_NAMES[lang] ?? lang} ({n})
                </div>
              </div>
            ))}
            <div className="tile">
              <div className="value tabular">{narratives.data?.length ?? '…'}</div>
              <div className="label">narratives</div>
            </div>
          </div>

          {stats.llm === 'unavailable' && (
            <p className="small secondary">
              Narrative names below are keyword-based: the LLM server was unreachable during this run. Start the SSH
              tunnel and run again for written labels.
            </p>
          )}

          {timeline.data && timeline.data.series.length > 0 && <CoverageTimeline timeline={timeline.data} />}

          <div className="cards">
            {narratives.data?.map((n, i) => (
              <div className="card" key={n.id}>
                <div className="card-title">
                  <span className="swatch" style={{ background: seriesColor(i) }} />
                  <div>
                    <div className="eyebrow">Narrative {String(i + 1).padStart(2, '0')}</div>
                    <h3>{n.label}</h3>
                  </div>
                </div>
                <div className="row small">
                  <span>
                    <b className="tabular">{n.volume}</b> items
                  </span>
                  <span className="muted">·</span>
                  <span>{n.unique_sources} sources</span>
                  <span className="muted">·</span>
                  <Growth growth={n.growth_pct} isNew={n.is_new} />
                  {n.spikes.length > 0 && <span className="badge">Spike</span>}
                </div>
                <SentimentBar sentiment={n.sentiment} />
                <LanguageSplit languages={n.languages} />
                <EntityChips entities={n.top_entities} limit={5} />
                <div>
                  <Link className="button ghost" to={`/narratives/${n.id}`} state={{ colorIndex: i }}>
                    Investigate
                  </Link>
                </div>
              </div>
            ))}
          </div>
          {narratives.data?.length === 0 && <p className="muted">No narratives found in this window.</p>}
        </>
      )}
    </div>
  )
}
