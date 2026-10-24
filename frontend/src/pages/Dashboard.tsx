import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { api, LANGUAGE_NAMES, type Monitor, type NarrativeCard, type Run, type Timeline } from '../api/client'
import { Arrow, EntityChips, Growth, LanguageSplit, SentimentBar } from '../components/Bits'
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
  const found = narratives.data?.length
  const clustered = narratives.data?.reduce((sum, n) => sum + n.volume, 0)

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <Link to="/monitors" className="back">
            ← All monitors
          </Link>
          <div className="eyebrow">Narrative command center</div>
          <h1>{m.topic}</h1>
          {run?.window_start && (
            <div className="meta muted small">
              {shortTime(run.window_start)} to {shortTime(run.window_end)} · {m.languages.map((l) => LANGUAGE_NAMES[l] ?? l).join(' + ')}
            </div>
          )}
        </div>
        <div className="row">
          <button className="ghost" onClick={() => rerun.mutate()} disabled={busy}>
            Run again
          </button>
          {completed && stats.outcome !== 'insufficient_coverage' && (
            <Link className="button dark" to={`/monitors/${id}/brief`}>
              Intelligence brief <Arrow size={14} />
            </Link>
          )}
        </div>
      </div>

      {run && !completed && <RunProgress run={run} />}

      {completed && stats.outcome === 'insufficient_coverage' && <InsufficientCoverage run={run!} />}

      {completed && stats.outcome !== 'insufficient_coverage' && (
        <>
          <div className="bento">
            <div className="card accent span-4">
              <div className="card-head">
                <span className="small">Articles analysed</span>
                <span className="pill-stat">{stats.unique_sources ?? 'n/a'} sources</span>
              </div>
              <div className="big-num">{total}</div>
              <div className="small secondary">
                {found == null ? '…' : `grouped into ${found} narrative${found === 1 ? '' : 's'}`}
                {clustered != null && total > 0 && ` · ${clustered} articles clustered`}
              </div>
            </div>

            <div className="card span-4">
              <div className="card-head">
                <span className="small secondary">Language coverage</span>
              </div>
              <div className="stat-grid">
                {Object.entries(byLang).map(([lang, n]) => (
                  <div key={lang}>
                    <div className="mid-num">{n}</div>
                    <div className="stat-label">
                      <i className="swatch" style={{ background: `var(--lang-${lang}, var(--series-other))`, width: 8, height: 8, marginRight: 5 }} />
                      {LANGUAGE_NAMES[lang] ?? lang}
                    </div>
                  </div>
                ))}
              </div>
              <div className="split" aria-hidden>
                {Object.entries(byLang).map(([lang, n]) => (
                  <span key={lang} style={{ flex: n, background: `var(--lang-${lang}, var(--series-other))` }} />
                ))}
              </div>
              <div className="stat-label" style={{ marginTop: 'auto' }}>
                {Object.entries(byLang)
                  .map(([lang, n]) => `${pct(total ? n / total : 0)} ${LANGUAGE_NAMES[lang] ?? lang}`)
                  .join(' · ')}
                {' '}of the coverage, analysed together in one embedding space
              </div>
            </div>

            <div className="card ink span-4">
              <div className="card-head">
                <span className="small muted">Fastest-growing narrative</span>
              </div>
              <FastestGrowing narratives={narratives.data} />
            </div>

            {stats.llm === 'unavailable' && (
              <div className="card soft span-12 small secondary">
                Narrative titles below are each narrative's most representative headline: the LLM was unreachable during
                this run. Check the LLM status at the top and run again for written narrative statements.
              </div>
            )}

            {timeline.data && timeline.data.series.length > 0 && (
              <CoverageTimeline timeline={timeline.data} className="span-12" />
            )}
          </div>

          <div className="section-title" style={{ marginTop: 18, marginBottom: 0 }}>
            <h2 className="serif" style={{ fontSize: '2rem' }}>Narratives</h2>
            <span className="muted small">Largest first · each colour matches its line in the chart</span>
          </div>
          <div className="narratives">
            {narratives.data?.map((n, i) => (
              <div className="card narrative-card" key={n.id}>
                <div className="spread">
                  <span className="n-index">
                    <span className="swatch" style={{ background: seriesColor(i) }} />
                    Narrative {String(i + 1).padStart(2, '0')}
                  </span>
                  <span className="row" style={{ gap: 6 }}>
                    <Growth growth={n.growth_pct} isNew={n.is_new} />
                    {n.spikes.length > 0 && <span className="badge spike">Spike</span>}
                  </span>
                </div>
                <h3>{n.label}</h3>
                <div className="metric-line">
                  <span>
                    <b className="tabular">{n.volume}</b> articles
                  </span>
                  <span>
                    <b className="tabular">{n.unique_sources}</b> sources
                  </span>
                </div>
                <SentimentBar sentiment={n.sentiment} />
                <LanguageSplit languages={n.languages} />
                <EntityChips entities={n.top_entities} limit={5} />
                <div className="foot">
                  <span />
                  <Link className="button ghost small" to={`/narratives/${n.id}`} state={{ colorIndex: i }}>
                    Investigate <Arrow size={13} />
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

function FastestGrowing({ narratives }: { narratives: NarrativeCard[] | undefined }) {
  if (!narratives) return <span className="muted small">…</span>
  const ranked = narratives
    .map((n, i) => ({ n, i }))
    .filter(({ n }) => n.is_new || n.growth_pct != null)
    .sort((a, b) => Number(b.n.is_new) - Number(a.n.is_new) || (b.n.growth_pct ?? 0) - (a.n.growth_pct ?? 0))
  const top = ranked[0]
  if (!top) return <span className="muted small">No growth measured in this window.</span>
  return (
    <Link to={`/narratives/${top.n.id}`} state={{ colorIndex: top.i }} style={{ color: 'inherit', textDecoration: 'none' }} className="stack">
      <span className="serif" style={{ fontSize: '1.35rem', lineHeight: 1.15 }}>
        {top.n.label}
      </span>
      <span className="mid-num" style={{ color: 'var(--red)' }}>
        {top.n.is_new ? 'New' : `${(top.n.growth_pct ?? 0) > 0 ? '+' : ''}${(top.n.growth_pct ?? 0).toFixed(0)}%`}
      </span>
      <span className="tiny muted">
        {top.n.is_new ? 'appeared only in the second half of the window' : 'articles, second half of the window vs the first'}
      </span>
    </Link>
  )
}

/** Where the articles went, for a run that found no narratives. */
function InsufficientCoverage({ run }: { run: Run }) {
  const s = run.stats
  const rss = s.sources?.rss ?? {}
  const steps: [string, number | undefined][] = [
    ['headlines read from the news feeds', rss.headlines],
    ['published in the selected time window', rss.in_window],
    ['matched the topic keywords', s.collected as number | undefined],
    ['unique articles after removing duplicates', s.enriched as number | undefined],
    ['relevant enough to the topic', s.relevant],
  ]
  const shown = steps.filter(([, v]) => v != null) as [string, number][]
  const max = Math.max(1, ...shown.map(([, v]) => v))
  return (
    <div className="bento">
      <div className="card span-7">
        <h2 className="serif" style={{ fontSize: '1.8rem' }}>
          Not enough coverage to find narratives
        </h2>
        <p className="secondary" style={{ margin: 0 }}>
          {run.message}
        </p>
        <div className="stack" style={{ gap: 10 }}>
          {shown.map(([label, v], i) => (
            <div key={label}>
              <div className="spread small">
                <span className="secondary">{label}</span>
                <b className="tabular">{v}</b>
              </div>
              <div className="progress" style={{ marginTop: 4 }}>
                <div style={{ width: `${Math.max(1, (v / max) * 100)}%`, opacity: 1 - i * 0.12 }} />
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="card ink span-5">
        <h3>What to try</h3>
        <p className="small secondary" style={{ margin: 0 }}>
          The feeds only hold each outlet's most recent stories, roughly the last 1 to 3 days. A topic needs about 25
          articles before storylines form.
        </p>
        <ul className="small" style={{ margin: 0, paddingLeft: '1.1em', lineHeight: 1.8 }}>
          <li>Pick one of the stories under “In the news now”</li>
          <li>Use the 3 day window</li>
          <li>Keep both English and Hindi selected</li>
        </ul>
        <Link to="/" className="button" style={{ marginTop: 'auto', alignSelf: 'flex-start' }}>
          See trending stories
        </Link>
      </div>
    </div>
  )
}
