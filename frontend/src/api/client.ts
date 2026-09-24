export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${await res.text()}`)
  return res.json() as Promise<T>
}

export type Health = {
  status: string
  db: { ok: boolean; dialect?: string; error?: string }
  llm: { ok: boolean; url: string; models?: string[]; hint?: string }
}
