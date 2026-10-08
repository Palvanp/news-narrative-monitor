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
      <div className="spread">
        <div>
          <Link to={`/monitors/${id}`} className="small">
            ← {monitor.data?.topic ?? 'Monitor'}
          </Link>
          <div className="eyebrow" style={{ marginTop: 8 }}>
            Intelligence brief
          </div>
          <h1>{monitor.data?.topic}</h1>
          {b?.content && <div className="muted small">{b.content.window} · generated {shortTime(b.created_at)} by {b.model}</div>}
        </div>
        <div className="row">
          {b?.markdown && (
            <button className="ghost" onClick={() => download(`nazar-brief-${id}.md`, b.markdown!)}>
              Export Markdown
            </button>
          )}
          <button onClick={() => generate.mutate()} disabled={busy}>
            {busy ? 'Generating…' : b ? 'Regenerate' : 'Generate brief'}
          </button>
        </div>
      </div>

      {generate.error && <p className="error">{generate.error.message}</p>}
      {busy && (
        <div className="panel">
          <p className="secondary">
            Writing the brief. This usually takes under a minute, longer if the LLM's rate limit is reached.
          </p>
        </div>
      )}
      {b?.status === 'failed' && (
        <div className="panel">
          <h2 className="error">Brief generation failed</h2>
          <p>{b.error}</p>
        </div>
      )}
      {b == null && !busy && !brief.isLoading && <p className="muted">No brief yet. Generate one from the latest completed run.</p>}

      {narratives.data && narratives.data.length > 0 && (
        <div className="panel">
          <div className="spread">
            <h2>Observed metrics</h2>
            <span className="badge">Measured, not generated</span>
          </div>
          <div className="table-scroll">
            <table className="data" style={{ marginTop: 8 }}>
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
          <div className="panel stack brief">
            <div className="spread">
              <h2>Assessment</h2>
              <span className="badge">
                Interpretation · {a.metrics.supported_claims}/{a.metrics.claims} claims cited
              </span>
            </div>
            <p>{withCitations(a.executive_summary)}</p>

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
              <>
                <h3 className="muted">Removed: statements without supporting evidence</h3>
                <ul className="muted">
                  {a.unsupported_claims.map((c, i) => (
                    <li key={i}>
                      <s>{c}</s>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>

          <div className="panel stack">
            <h2>Evidence</h2>
            <div className="evidence">
              {Object.values(b.content.evidence).map((e) => (
                <div key={e.id} id={e.id} className="evidence-item rep">
                  <div className="small">
                    <b>{e.id}</b>{' '}
                    <a href={e.url} target="_blank" rel="noreferrer">
                      {e.title}
                    </a>
                  </div>
                  <div className="muted small">
                    {e.source} · {LANGUAGE_NAMES[e.language ?? ''] ?? e.language} · {shortTime(e.published_at)}
                  </div>
                  {e.excerpt && <blockquote>“{e.excerpt}”</blockquote>}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
