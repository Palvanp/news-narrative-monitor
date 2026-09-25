export function pct(value: number | undefined | null, digits = 0): string {
  return value == null ? 'n/a' : `${(value * 100).toFixed(digits)}%`
}

export function shortTime(iso: string | null | undefined): string {
  if (!iso) return 'n/a'
  const d = new Date(iso)
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function hourLabel(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString(undefined, { day: 'numeric', hour: '2-digit' })
}

// Narrative colors follow the narrative's position in the volume-sorted list of
// its run, so a card and its timeline series always share a color.
export const MAX_SERIES = 7

export function seriesColor(index: number): string {
  return index < MAX_SERIES ? `var(--series-${index + 1})` : 'var(--series-other)'
}
