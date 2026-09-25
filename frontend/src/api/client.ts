export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export type Health = {
  status: string
  db: { ok: boolean; dialect?: string; error?: string }
  llm: { ok: boolean; url: string; models?: string[]; hint?: string }
}

export type RunStats = {
  collected?: number
  stored?: number
  enriched?: number
  unique_sources?: number
  by_language?: Record<string, number>
  narratives?: number
  unclustered?: number
  llm?: string
  outcome?: 'narratives' | 'insufficient_coverage'
  relevant?: number
  below_relevance?: number
  sources?: { rss?: { feeds_ok?: number; headlines?: number; in_window?: number; matched?: number } }
  timings_s?: Record<string, number>
  [key: string]: unknown
}

export type Run = {
  id: number
  monitor_id: number
  status: 'pending' | 'running' | 'completed' | 'failed'
  stage: string | null
  progress: number
  message: string | null
  error: string | null
  window_start: string | null
  window_end: string | null
  stats: RunStats
  started_at: string | null
  finished_at: string | null
}

export type Monitor = {
  id: number
  topic: string
  hindi_keywords: string | null
  languages: string[]
  time_range_hours: number
  created_at: string
  latest_run: Run | null
}

export type EntityRef = { id: number; name: string; type: string; articles: number }

export type NarrativeCard = {
  id: number
  run_id: number
  label: string
  label_source: 'llm' | 'headline' | 'keywords'
  summary: string | null
  keywords: string[]
  volume: number
  growth_pct: number | null
  is_new: boolean
  sentiment: Record<string, number>
  languages: Record<string, number>
  unique_sources: number
  spikes: string[]
  top_entities: EntityRef[]
}

export type NarrativeStats = {
  previous_window: number
  current_window: number
  sentiment_shift_pp: number | null
  first_seen: string | null
  last_seen: string | null
  top_sources: { domain: string; count: number }[]
  timeline: { edges: string[]; counts: number[] }
}

export type NarrativeDetail = NarrativeCard & { monitor_id: number; topic: string; stats: NarrativeStats }

export type EvidenceItem = {
  article_id: number
  title: string
  url: string
  source: string | null
  language: string | null
  published_at: string | null
  sentiment: string | null
  similarity: number
  is_representative: boolean
  evidence_text: string | null
  syndicated_copies: number
}

export type RelatedNarrative = { id: number; label: string; similarity: number }

export type Timeline = {
  run_id: number
  edges: string[]
  series: { narrative_id: number; label: string; counts: number[] }[]
}

export type Claim = { claim: string; evidence_ids: string[] }

export type BriefEvidence = {
  id: string
  article_id: number
  narrative_id: number
  title: string
  source: string | null
  language: string | null
  published_at: string
  url: string
  excerpt: string | null
}

export type Brief = {
  id: number
  run_id: number
  model: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  error: string | null
  markdown: string | null
  created_at: string
  content: {
    window: string
    evidence: Record<string, BriefEvidence>
    assessment: {
      executive_summary: string
      executive_summary_evidence: string[]
      key_developments: Claim[]
      narratives: { narrative_id: number; assessment: string; evidence_ids: string[] }[]
      narrative_shift: Claim | null
      key_entities: string[]
      unsupported_claims: string[]
      metrics: { claims: number; supported_claims: number; evidence_coverage: number | null }
    }
  } | null
}

export const LANGUAGE_NAMES: Record<string, string> = { en: 'English', hi: 'Hindi' }
