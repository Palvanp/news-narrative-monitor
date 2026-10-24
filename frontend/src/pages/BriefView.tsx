import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Fragment, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError, LANGUAGE_NAMES, type Brief, type Monitor, type NarrativeCard } from '../api/client'
import { Growth } from '../components/Bits'
import { pct, shortTime } from '../components/format'

/** Turns "[E3]" markers in generated text into links to the evidence list. */
function withCitations(text: string): ReactNode {
  return text.split(/(\[E\d+\])/g).map((part, i) => {
    const m = part.match(/^\[(E\d+)\]$/)
    return m ? (
      <a key={i} className="cite" href={`#${m[1]}`}>
        {m[1]}
      </a>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    )
  })
}

function Citations({ ids }: { ids: string[] }) {
  return (
    <>
      {ids.map((id) => (
        <a key={id} className="cite" href={`#${id}`}>
          {id}
        </a>
      ))}
    </>
  )
}

function download(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/markdown' }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export default function BriefView() {
  const id = Number(useParams().id)
  const queryClient = useQueryClient()
  const monitor = useQuery({ queryKey: ['monitor', id], queryFn: () => api<Monitor>(`/monitors/${id}`) })
  const narratives = useQuery({ queryKey: ['narratives', id], queryFn: () => api<NarrativeCard[]>(`/monitors/${id}/narratives`) })
  const brief = useQuery({
    queryKey: ['brief', id],
    queryFn: async () => {
      try {
        return await api<Brief>(`/monitors/${id}/brief`)
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null
        throw e
      }
    },
    refetchInterval: (q) => (q.state.data && ['pending', 'running'].includes(q.state.data.status) ? 4000 : false),
  })
  const generate = useMutation({
    mutationFn: () => api<Brief>(`/monitors/${id}/brief`, { method: 'POST' }),
    onSuccess: (b) => queryClient.setQueryData(['brief', id], b),
  })

  const b = brief.data
  const busy = generate.isPending || (b != null && ['pending', 'running'].includes(b.status))
  const a = b?.content?.assessment
  const labels = new Map(narratives.data?.map((n) => [n.id, n.label]))

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <Link to={`/monitors/${id}`} className="back">
            ← {monitor.data?.topic ?? 'Monitor'}
          </Link>
          <div className="eyebrow">Intelligence brief</div>
          <h1>{monitor.data?.topic}</h1>
          {b?.content && (
            <div className="meta muted small">
              {b.content.window} · generated {shortTime(b.created_at)} by {b.model}
            </div>
          )}
        </div>
        <div className="row">
          {b?.markdown && (
            <button className="ghost" onClick={() => download(`nazar-brief-${id}.md`, b.markdown!)}>
              Export Markdown
            </button>
          )}
          <button className={b ? 'dark' : ''} onClick={() => generate.mutate()} disabled={busy}>
            {busy ? 'Generating…' : b ? 'Regenerate' : 'Generate brief'}
          </button>
        </div>
      </div>

      {generate.error && <p className="error">{generate.error.message}</p>}
      {busy && (
        <div className="card">
          <div className="skeleton" style={{ minHeight: 8, borderRadius: 999 }} />
          <p className="secondary" style={{ margin: 0 }}>
            Writing the brief. This usually takes under a minute, longer if the LLM's rate limit is reached.
          </p>
        </div>
      )}
      {b?.status === 'failed' && (
        <div className="card">
          <h2 className="error">Brief generation failed</h2>
          <p style={{ margin: 0 }}>{b.error}</p>
        </div>
      )}
      {b == null && !busy && !brief.isLoading && (
        <div className="card soft empty">
          <h2>No brief yet</h2>
          <p>Generate one from the latest completed run. Every claim it keeps will cite an article.</p>
        </div>
      )}

      {a && b?.content && (
        <div className="bento">
          <div className="card accent span-4">
            <span className="small">Claims backed by evidence</span>
            <span className="big-num">
              {a.metrics.supported_claims}
              <span style={{ opacity: 0.7, fontWeight: 400 }}>/{a.metrics.claims}</span>
            </span>
            <span className="small secondary">claims in the brief that cite at least one article</span>
          </div>
          <div className="card span-4">
            <span className="small secondary">Evidence articles</span>
            <span className="big-num">{Object.keys(b.content.evidence).length}</span>
            <span className="stat-label">available to the LLM to cite, quoted on the right</span>
          </div>
          <div className="card span-4">
            <span className="small secondary">Removed statements</span>
            <span className="big-num">{a.unsupported_claims.length}</span>
            <span className="stat-label">had no supporting article, so they were struck out</span>
          </div>
        </div>
      )}

      {narratives.data && narratives.data.length > 0 && (
        <div className="card">
          <div className="card-head">
            <h2>Observed metrics</h2>
            <span className="badge">Measured, not generated</span>
          </div>
          <div className="table-scroll">
            <table className="data">
              <thead>
                <tr>
                  <th>Narrative</th>
                  <th className="num">Articles</th>
                  <th>Growth</th>
                  <th className="num">Negative</th>
                  <th>Languages</th>
                </tr>
              </thead>
              <tbody>
                {narratives.data.map((n) => (
                  <tr key={n.id}>
                    <td>
                      <Link to={`/narratives/${n.id}`}>{n.label}</Link>
                    </td>
                    <td className="num">{n.volume}</td>
                    <td>
                      <Growth growth={n.growth_pct} isNew={n.is_new} />
                    </td>
                    <td className="num">{pct(n.sentiment.negative)}</td>
                    <td>
                      {Object.entries(n.languages)
                        .map(([k, v]) => `${LANGUAGE_NAMES[k] ?? k} ${pct(v)}`)
                        .join(', ')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {a && b?.content && (
        <div className="two-col">
          <article className="card brief" style={{ padding: 28 }}>
            <div className="spread">
              <h2>Assessment</h2>
              <span className="badge">Interpretation · written by the LLM</span>
            </div>
            <p className="lead">{withCitations(a.executive_summary)}</p>

            {a.key_developments.length > 0 && (
              <>
                <h3>Key developments</h3>
                <ul>
                  {a.key_developments.map((d, i) => (
                    <li key={i}>
                      {withCitations(d.claim)} <Citations ids={d.evidence_ids.filter((e) => !d.claim.includes(`[${e}]`))} />
                    </li>
                  ))}
                </ul>
              </>
            )}

            {a.narratives.map((n) => (
              <div key={n.narrative_id}>
                <h3>{labels.get(n.narrative_id) ?? `Narrative ${n.narrative_id}`}</h3>
                <p>
                  {withCitations(n.assessment)} <Citations ids={n.evidence_ids.filter((e) => !n.assessment.includes(`[${e}]`))} />
                </p>
              </div>
            ))}

            {a.narrative_shift && (
              <>
                <h3>Narrative shift</h3>
                <p>
                  {withCitations(a.narrative_shift.claim)}{' '}
                  <Citations ids={a.narrative_shift.evidence_ids.filter((e) => !a.narrative_shift!.claim.includes(`[${e}]`))} />
                </p>
              </>
            )}

            {a.unsupported_claims.length > 0 && (
              <div className="removed">
                <div className="small" style={{ fontWeight: 600, marginBottom: 4 }}>
                  Removed: statements without supporting evidence
                </div>
                <ul className="muted" style={{ margin: 0 }}>
                  {a.unsupported_claims.map((c, i) => (
                    <li key={i}>
                      <s>{c}</s>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </article>

          <div className="card" style={{ position: 'sticky', top: 16, maxHeight: 'calc(100vh - 32px)', overflowY: 'auto' }}>
            <h2>Evidence</h2>
            <div className="evidence">
              {Object.values(b.content.evidence).map((e) => (
                <div key={e.id} id={e.id} className="evidence-item rep">
                  <div className="small">
                    <span className="evidence-id">{e.id}</span>
                    <a className="title" href={e.url} target="_blank" rel="noreferrer" lang={e.language ?? undefined}>
                      {e.title}
                    </a>
                  </div>
                  <div className="muted tiny" style={{ marginTop: 4 }}>
                    {e.source} · {LANGUAGE_NAMES[e.language ?? ''] ?? e.language} · {shortTime(e.published_at)}
                  </div>
                  {e.excerpt && <blockquote lang={e.language ?? undefined}>“{e.excerpt}”</blockquote>}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
