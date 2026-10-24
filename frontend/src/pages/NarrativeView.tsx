import { useQuery } from '@tanstack/react-query'
import { Link, useLocation, useParams } from 'react-router-dom'
import { api, LANGUAGE_NAMES, type EvidenceItem, type NarrativeDetail, type RelatedNarrative } from '../api/client'
import { EntityChips, LanguageSplit, SentimentBar } from '../components/Bits'
import { NarrativeVolume } from '../components/Charts'
import { seriesColor, shortTime } from '../components/format'

type Milestone = { label: string; time: string; detail: string }

/** Key moments in how coverage developed, derived from article timestamps. */
function coverageMilestones(detail: NarrativeDetail, evidence: EvidenceItem[]): Milestone[] {
  const dated = evidence.filter((e) => e.published_at).sort((a, b) => a.published_at!.localeCompare(b.published_at!))
  const out: Milestone[] = []
  if (dated[0]) out.push({ label: 'First detected', time: dated[0].published_at!, detail: `${dated[0].source ?? 'unknown'}: ${dated[0].title}` })
  for (const lang of Object.keys(detail.languages)) {
    const first = dated.find((e) => e.language === lang)
    if (first && first !== dated[0]) {
      out.push({ label: `First ${LANGUAGE_NAMES[lang] ?? lang} coverage`, time: first.published_at!, detail: `${first.source ?? 'unknown'}: ${first.title}` })
    }
  }
  for (const spike of detail.spikes) {
    out.push({ label: 'Coverage spike', time: spike, detail: 'Volume well above the rest of the window' })
  }
  const last = dated[dated.length - 1]
  if (last && dated.length > 1) out.push({ label: 'Latest', time: last.published_at!, detail: `${last.source ?? 'unknown'}: ${last.title}` })
  return out.sort((a, b) => a.time.localeCompare(b.time))
}

export default function NarrativeView() {
  const id = Number(useParams().id)
  const colorIndex = (useLocation().state as { colorIndex?: number } | null)?.colorIndex ?? 0
  const color = seriesColor(colorIndex)

  const detail = useQuery({ queryKey: ['narrative', id], queryFn: () => api<NarrativeDetail>(`/narratives/${id}`) })
  const evidence = useQuery({ queryKey: ['evidence', id], queryFn: () => api<EvidenceItem[]>(`/narratives/${id}/evidence`) })
  const related = useQuery({ queryKey: ['related', id], queryFn: () => api<RelatedNarrative[]>(`/narratives/${id}/related`) })

  if (detail.isLoading) return <p className="muted">Loading…</p>
  if (detail.error || !detail.data) return <p className="error">{detail.error?.message ?? 'Not found'}</p>
  const n = detail.data
  const s = n.stats
  const items = evidence.data ?? []

  const prev = s.previous_window
  const cur = s.current_window

  return (
    <div className="stack">
      <div>
        <Link to={`/monitors/${n.monitor_id}`} className="back">
          ← {n.topic}
        </Link>
        <div className="eyebrow">Narrative investigation</div>
        <h1 style={{ maxWidth: '24ch' }}>
          <span className="swatch" style={{ background: color, width: 14, height: 14, marginRight: 12, verticalAlign: '0.25em' }} />
          {n.label}
        </h1>
        {n.label_source !== 'llm' && (
          <div className="muted small" style={{ marginTop: 8 }}>
            Provisional title: the most representative headline. The LLM writes a narrative statement when it is
            connected.
          </div>
        )}
        {n.summary && (
          <p className="secondary" style={{ maxWidth: '70ch', fontSize: '1.05rem', marginBottom: 0 }}>
            {n.summary}
          </p>
        )}
      </div>

      <div className="bento">
        <div className="card accent span-4">
          <div className="card-head">
            <span className="small">Coverage growth</span>
            {n.is_new ? <span className="pill-stat">New</span> : n.growth_pct != null && (
              <span className="pill-stat">
                {n.growth_pct > 0 ? '+' : ''}
                {n.growth_pct.toFixed(0)}%
              </span>
            )}
          </div>
          <div className="big-num">
            {prev} <span style={{ opacity: 0.7, fontWeight: 400 }}>→</span> {cur}
          </div>
          <div className="small secondary">articles, first half of the window → second half</div>
        </div>
        <div className="card span-3">
          <span className="small secondary">Articles</span>
          <span className="big-num">{n.volume}</span>
          <span className="stat-label">from {n.unique_sources} sources</span>
        </div>
        <div className="card span-5">
          <span className="small secondary">Change in negative coverage</span>
          <span className="big-num">
            {s.sentiment_shift_pp == null ? 'n/a' : `${s.sentiment_shift_pp > 0 ? '+' : s.sentiment_shift_pp < 0 ? '−' : ''}${Math.abs(s.sentiment_shift_pp).toFixed(0)} pts`}
          </span>
          <span className="stat-label">share of negative articles, second half vs first half</span>
        </div>
      </div>

      <div className="two-col">
        <div className="stack">
          <div className="card">
            <div className="card-head">
              <h2>Coverage over time</h2>
              {n.spikes.length > 0 && <span className="badge spike">{n.spikes.length} spike{n.spikes.length > 1 ? 's' : ''}</span>}
            </div>
            <NarrativeVolume edges={s.timeline.edges} counts={s.timeline.counts} spikes={n.spikes} color={color} />
            <div className="timeline-list">
              {coverageMilestones(n, items).map((m, i) => (
                <div key={i}>
                  <span className="muted tabular">{shortTime(m.time)}</span>
                  <span className="tl-dot" />
                  <span>
                    <b>{m.label}</b> <span className="secondary">{m.detail}</span>
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="card-head">
              <h2>Evidence</h2>
              <span className="muted small">Representative articles first · {items.length} shown</span>
            </div>
            <div className="evidence">
              {items.map((e) => (
                <div key={e.article_id} className={`evidence-item ${e.is_representative ? 'rep' : ''}`}>
                  <a className="title" href={e.url} target="_blank" rel="noreferrer" lang={e.language ?? undefined}>
                    {e.title}
                  </a>
                  <div className="muted tiny" style={{ marginTop: 4 }}>
                    {e.source ?? 'unknown source'} · {LANGUAGE_NAMES[e.language ?? ''] ?? e.language} · {shortTime(e.published_at)}
                    {e.sentiment && ` · ${e.sentiment}`} · similarity {e.similarity.toFixed(2)}
                    {e.syndicated_copies > 0 && ` · +${e.syndicated_copies} syndicated copies`}
                  </div>
                  {e.evidence_text && <blockquote lang={e.language ?? undefined}>“{e.evidence_text}”</blockquote>}
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="stack">
          <div className="card">
            <h3>Sentiment</h3>
            <SentimentBar sentiment={n.sentiment} />
            <h3>Languages</h3>
            <LanguageSplit languages={n.languages} />
          </div>
          <div className="card">
            <h3>Entities</h3>
            <EntityChips entities={n.top_entities} limit={12} />
            {n.keywords.length > 0 && (
              <>
                <h3>Keywords</h3>
                <div className="chips">
                  {n.keywords.map((k) => (
                    <span className="chip" key={k}>
                      {k}
                    </span>
                  ))}
                </div>
              </>
            )}
          </div>
          <div className="card">
            <h3>Top sources</h3>
            <table className="data">
              <tbody>
                {s.top_sources.map((src) => (
                  <tr key={src.domain}>
                    <td>{src.domain}</td>
                    <td className="num">{src.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!!related.data?.length && (
            <div className="card ink">
              <h3>Related narratives</h3>
              {related.data.map((r) => (
                <Link key={r.id} to={`/narratives/${r.id}`} className="spread small" style={{ color: 'inherit', textDecoration: 'none', flexWrap: 'nowrap' }}>
                  <span>{r.label}</span>
                  <span className="muted tabular">{r.similarity.toFixed(2)}</span>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
