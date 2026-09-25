import { useQuery } from '@tanstack/react-query'
import { Link, useLocation, useParams } from 'react-router-dom'
import { api, LANGUAGE_NAMES, type EvidenceItem, type NarrativeDetail, type RelatedNarrative } from '../api/client'
import { EntityChips, Growth, LanguageSplit, SentimentBar } from '../components/Bits'
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

  return (
    <div className="stack">
      <div>
        <Link to={`/monitors/${n.monitor_id}`} className="small">
          ← {n.topic}
        </Link>
        <div className="card-title" style={{ marginTop: 8 }}>
          <span className="swatch" style={{ background: color }} />
          <div>
            <div className="eyebrow">Narrative investigation</div>
            <h1>{n.label}</h1>
            {n.label_source === 'keywords' && <div className="muted small">Keyword label (LLM was unavailable)</div>}
          </div>
        </div>
        {n.summary && <p className="secondary">{n.summary}</p>}
      </div>

      <div className="tiles">
        <div className="tile">
          <div className="value tabular">{n.volume}</div>
          <div className="label">articles</div>
        </div>
        <div className="tile">
          <div className="value">
            <Growth growth={n.growth_pct} isNew={n.is_new} />
          </div>
          <div className="label">
            coverage growth ({s.previous_window} → {s.current_window})
          </div>
        </div>
        <div className="tile">
          <div className="value tabular">
            {s.sentiment_shift_pp == null ? 'n/a' : `${s.sentiment_shift_pp > 0 ? '+' : ''}${s.sentiment_shift_pp.toFixed(0)} pp`}
          </div>
          <div className="label">change in negative share</div>
        </div>
        <div className="tile">
          <div className="value tabular">{n.unique_sources}</div>
          <div className="label">sources</div>
        </div>
      </div>

      <div className="two-col">
        <div className="stack">
          <div className="panel stack">
            <h2>Coverage over time</h2>
            <NarrativeVolume edges={s.timeline.edges} counts={s.timeline.counts} spikes={n.spikes} color={color} />
            <div className="stack" style={{ gap: 8 }}>
              {coverageMilestones(n, items).map((m, i) => (
                <div key={i} className="row small" style={{ alignItems: 'flex-start', flexWrap: 'nowrap' }}>
                  <span className="muted tabular" style={{ minWidth: 110 }}>{shortTime(m.time)}</span>
                  <span>
                    <b>{m.label}</b> <span className="secondary">{m.detail}</span>
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="panel stack">
            <div className="spread">
              <h2>Evidence</h2>
              <span className="muted small">Representative articles first · {items.length} shown</span>
            </div>
            <div className="evidence">
              {items.map((e) => (
                <div key={e.article_id} className={`evidence-item ${e.is_representative ? 'rep' : ''}`}>
                  <a href={e.url} target="_blank" rel="noreferrer">
                    {e.title}
                  </a>
                  <div className="muted small">
                    {e.source ?? 'unknown source'} · {LANGUAGE_NAMES[e.language ?? ''] ?? e.language} · {shortTime(e.published_at)}
                    {e.sentiment && ` · ${e.sentiment}`} · similarity {e.similarity.toFixed(2)}
                    {e.syndicated_copies > 0 && ` · +${e.syndicated_copies} syndicated copies`}
                  </div>
                  {e.evidence_text && <blockquote>“{e.evidence_text}”</blockquote>}
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="stack">
          <div className="panel stack">
            <h3>Sentiment</h3>
            <SentimentBar sentiment={n.sentiment} />
            <h3>Languages</h3>
            <LanguageSplit languages={n.languages} />
          </div>
          <div className="panel stack">
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
          <div className="panel stack">
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
            <div className="panel stack">
              <h3>Related narratives</h3>
              {related.data.map((r) => (
                <div key={r.id} className="spread small">
                  <Link to={`/narratives/${r.id}`}>{r.label}</Link>
                  <span className="muted tabular">{r.similarity.toFixed(2)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
