import { useState } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { Timeline } from '../api/client'
import { MAX_SERIES, hourLabel, seriesColor, shortTime } from './format'

type Row = Record<string, number | string>

const axisProps = {
  stroke: 'var(--axis)',
  tick: { fill: 'var(--text-muted)', fontSize: 11 },
  tickLine: false,
}

function TooltipBox({ active, payload, label }: { active?: boolean; payload?: { name: string; value: number; color: string }[]; label?: string }) {
  if (!active || !payload?.length) return null
  const rows = payload.filter((p) => p.value > 0)
  return (
    <div className="chart-tooltip">
      <div className="muted">{shortTime(label)}</div>
      {rows.length === 0 && <div>No articles</div>}
      {rows.map((p) => (
        <div className="row" key={p.name}>
          <span className="swatch" style={{ background: p.color, marginTop: 0 }} />
          <span>{p.name}</span>
          <b className="tabular" style={{ marginLeft: 'auto' }}>{p.value}</b>
        </div>
      ))}
    </div>
  )
}

/** Stacked narrative coverage over the window. Past MAX_SERIES narratives fold into "Other". */
export function CoverageTimeline({ timeline }: { timeline: Timeline }) {
  const [asTable, setAsTable] = useState(false)
  const shown = timeline.series.slice(0, MAX_SERIES)
  const rest = timeline.series.slice(MAX_SERIES)
  const keys = shown.map((s) => s.label).concat(rest.length ? ['Other narratives'] : [])
  const starts = timeline.edges.slice(0, -1)

  const rows: Row[] = starts.map((edge, i) => {
    const row: Row = { t: edge }
    shown.forEach((s) => (row[s.label] = s.counts[i] ?? 0))
    if (rest.length) row['Other narratives'] = rest.reduce((sum, s) => sum + (s.counts[i] ?? 0), 0)
    return row
  })

  return (
    <div className="panel">
      <div className="spread">
        <h2>Narrative coverage over time</h2>
        <button className="ghost small" onClick={() => setAsTable(!asTable)}>
          {asTable ? 'Show chart' : 'Show table'}
        </button>
      </div>
      {asTable ? (
        <div className="table-scroll" style={{ marginTop: 12 }}>
          <table className="data">
            <thead>
              <tr>
                <th>Hour starting</th>
                {keys.map((k) => (
                  <th className="num" key={k}>{k}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={String(r.t)}>
                  <td>{shortTime(String(r.t))}</td>
                  {keys.map((k) => (
                    <td className="num" key={k}>{r[k]}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <>
          <div style={{ width: '100%', height: 260, marginTop: 12 }}>
            <ResponsiveContainer>
              <AreaChart data={rows} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid stroke="var(--grid)" vertical={false} />
                <XAxis dataKey="t" tickFormatter={hourLabel} minTickGap={32} {...axisProps} />
                <YAxis allowDecimals={false} axisLine={false} {...axisProps} />
                <Tooltip content={<TooltipBox />} cursor={{ stroke: 'var(--axis)' }} />
                {keys.map((k, i) => (
                  <Area
                    key={k}
                    type="monotone"
                    dataKey={k}
                    name={k}
                    stackId="coverage"
                    stroke={seriesColor(i)}
                    strokeWidth={2}
                    fill={seriesColor(i)}
                    fillOpacity={0.55}
                    activeDot={{ r: 4, stroke: 'var(--surface)', strokeWidth: 2 }}
                    isAnimationActive={false}
                  />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="split-legend" style={{ marginTop: 8 }}>
            {keys.map((k, i) => (
              <span key={k}>
                <i style={{ background: seriesColor(i) }} />
                {k}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

/** One narrative's article count per time bin, with spike bins emphasized. */
export function NarrativeVolume({ edges, counts, spikes, color }: { edges: string[]; counts: number[]; spikes: string[]; color: string }) {
  const spikeSet = new Set(spikes)
  const rows = edges.slice(0, -1).map((t, i) => ({ t, count: counts[i] ?? 0, spike: spikeSet.has(t) }))
  return (
    <div style={{ width: '100%', height: 180 }}>
      <ResponsiveContainer>
        <BarChart data={rows} margin={{ top: 8, right: 8, left: -16, bottom: 0 }} barCategoryGap={2}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="t" tickFormatter={hourLabel} minTickGap={32} {...axisProps} />
          <YAxis allowDecimals={false} axisLine={false} {...axisProps} />
          <Tooltip
            cursor={{ fill: 'var(--grid)', opacity: 0.5 }}
            content={({ active, payload }) =>
              active && payload?.length ? (
                <div className="chart-tooltip">
                  <div className="muted">{shortTime(String(payload[0].payload.t))}</div>
                  <div>
                    <b className="tabular">{payload[0].payload.count}</b> articles
                    {payload[0].payload.spike ? ' · spike' : ''}
                  </div>
                </div>
              ) : null
            }
          />
          <Bar
            dataKey="count"
            radius={[4, 4, 0, 0]}
            isAnimationActive={false}
            shape={(props: unknown) => {
              const p = props as { x: number; y: number; width: number; height: number; payload: { spike: boolean } }
              if (!p.height) return <g />
              const r = Math.min(4, p.width / 2, p.height)
              const { x, y, width: w, height: h } = p
              return (
                <path
                  d={`M${x},${y + h} V${y + r} Q${x},${y} ${x + r},${y} H${x + w - r} Q${x + w},${y} ${x + w},${y + r} V${y + h} Z`}
                  fill={color}
                  fillOpacity={p.payload.spike ? 1 : 0.6}
                />
              )
            }}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
