/**
 * DataBlocks — renders the structured answer blocks the engine streams for data questions:
 * a result table (always available as the accessible view) and an optional declarative chart
 * (kpi | line | bar) drawn as inline SVG. The chart spec comes from the backend's safe schema;
 * no model-generated code is ever executed.
 */

import { useMemo, useState } from 'react';
import type { AnswerBlock, ChartBlockData, TableBlockData } from '@/types';

// Dark-surface palette (categorical slots 1-3 from the reference palette) and text tokens.
const SERIES = ['#3987e5', '#d95926', '#199e70'];
const TEXT_PRIMARY = '#f0efec';
const TEXT_SECONDARY = '#c3c2b7';
const GRID = '#2b2b2a';

function formatNumber(v: unknown): string {
    if (typeof v !== 'number') return v === null || v === undefined ? '' : String(v);
    const abs = Math.abs(v);
    if (abs >= 1_000_000) return `${(v / 1_000_000).toFixed(abs >= 10_000_000 ? 0 : 1)}M`;
    if (abs >= 1_000) return `${(v / 1_000).toFixed(abs >= 10_000 ? 0 : 1)}K`;
    return Number.isInteger(v) ? String(v) : v.toFixed(2);
}

function niceTicks(max: number, count = 4): number[] {
    if (max <= 0) return [0];
    const raw = max / count;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
    const ticks: number[] = [];
    for (let t = 0; t <= max + step * 0.001; t += step) ticks.push(Math.round(t * 1e6) / 1e6);
    return ticks;
}

export function TableBlock({ data }: { data: TableBlockData }) {
    const [expanded, setExpanded] = useState(false);
    const rows = expanded ? data.rows : data.rows.slice(0, 10);
    return (
        <div className="mt-3 rounded-xl border border-dark-700 bg-dark-900/60 overflow-hidden">
            <div className="flex items-center justify-between px-3 py-2 text-[11px] text-dark-400">
                <span>{data.connection} · {data.row_count} row{data.row_count === 1 ? '' : 's'}</span>
                <details className="group">
                    <summary className="cursor-pointer select-none hover:text-dark-200">SQL</summary>
                    <pre className="mt-2 max-w-[70vw] overflow-x-auto rounded bg-dark-950 p-2 text-[11px] text-dark-300 whitespace-pre-wrap">{data.sql}</pre>
                </details>
            </div>
            <div className="overflow-x-auto">
                <table className="w-full text-xs">
                    <thead>
                        <tr className="text-left text-dark-400 border-t border-b border-dark-700">
                            {data.columns.map((c) => (
                                <th key={c} className="px-3 py-1.5 font-medium">{c}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((r, i) => (
                            <tr key={i} className="border-b border-dark-800/80 text-dark-200">
                                {r.map((v, j) => (
                                    <td key={j} className={'px-3 py-1 ' + (typeof v === 'number' ? 'text-right tabular-nums' : '')}>
                                        {typeof v === 'number' ? v.toLocaleString() : v === null ? '' : String(v)}
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            {data.rows.length > 10 && (
                <button onClick={() => setExpanded(!expanded)} className="w-full py-1.5 text-[11px] text-dark-400 hover:text-dark-200">
                    {expanded ? 'Show fewer rows' : `Show all ${data.rows.length} rows`}
                </button>
            )}
        </div>
    );
}

function KpiChart({ data }: { data: ChartBlockData }) {
    return (
        <div className="mt-3 inline-flex flex-col rounded-xl border border-dark-700 bg-dark-900/60 px-5 py-4 min-w-[180px]">
            <span className="text-[11px] text-dark-400">{data.label || data.title}</span>
            <span className="text-2xl font-semibold tabular-nums" style={{ color: TEXT_PRIMARY }}>
                {typeof data.value === 'number' ? data.value.toLocaleString() : String(data.value ?? '')}
            </span>
        </div>
    );
}

function SeriesChart({ data, table }: { data: ChartBlockData; table?: TableBlockData }) {
    const [hover, setHover] = useState<number | null>(null);
    const width = 560, height = 240;
    const pad = { l: 48, r: 16, t: 16, b: 36 };
    const plotW = width - pad.l - pad.r, plotH = height - pad.t - pad.b;

    const model = useMemo(() => {
        if (!table || !data.x || !data.y?.length) return null;
        const xi = table.columns.indexOf(data.x);
        const yis = data.y.map((y) => table.columns.indexOf(y)).filter((i) => i >= 0);
        if (xi < 0 || !yis.length) return null;
        const rows = table.rows.slice(0, 60);
        const labels = rows.map((r) => String(r[xi] ?? ''));
        const series = yis.map((yi) => rows.map((r) => (typeof r[yi] === 'number' ? (r[yi] as number) : 0)));
        const max = Math.max(0, ...series.flat());
        return { labels, series, names: yis.map((i) => table.columns[i]), max: max || 1 };
    }, [data, table]);

    if (!model) return null;
    const ticks = niceTicks(model.max);
    const yMax = ticks[ticks.length - 1] || model.max;
    const yScale = (v: number) => pad.t + plotH - (v / yMax) * plotH;
    const n = model.labels.length;
    const isLine = data.type === 'line';
    const band = plotW / Math.max(n, 1);
    const groupW = Math.min(24 * model.series.length, band * 0.7);
    const barW = groupW / model.series.length;
    const xCenter = (i: number) => pad.l + band * i + band / 2;
    const labelEvery = Math.max(1, Math.ceil(n / 8));

    return (
        <div className="mt-3 rounded-xl border border-dark-700 bg-dark-900/60 p-3" onMouseLeave={() => setHover(null)}>
            <div className="text-[11px] mb-1" style={{ color: TEXT_SECONDARY }}>{data.title}</div>
            <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto" role="img" aria-label={data.title}>
                {ticks.map((t) => (
                    <g key={t}>
                        <line x1={pad.l} x2={width - pad.r} y1={yScale(t)} y2={yScale(t)} stroke={GRID} strokeWidth={1} />
                        <text x={pad.l - 6} y={yScale(t) + 3} textAnchor="end" fontSize={10} fill={TEXT_SECONDARY}>{formatNumber(t)}</text>
                    </g>
                ))}
                {model.labels.map((lab, i) => (
                    i % labelEvery === 0 && (
                        <text key={i} x={xCenter(i)} y={height - pad.b + 14} textAnchor="middle" fontSize={10} fill={TEXT_SECONDARY}>
                            {lab.length > 10 ? lab.slice(0, 9) + '…' : lab}
                        </text>
                    )
                ))}
                {model.series.map((vals, s) => {
                    const color = SERIES[s % SERIES.length];
                    if (isLine) {
                        const d = vals.map((v, i) => `${i === 0 ? 'M' : 'L'}${xCenter(i)},${yScale(v)}`).join(' ');
                        const last = vals.length - 1;
                        return (
                            <g key={s}>
                                <path d={d} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
                                {vals.map((v, i) => (
                                    (hover === i || i === last) && (
                                        <circle key={i} cx={xCenter(i)} cy={yScale(v)} r={4} fill={color} stroke="#1a1a19" strokeWidth={2} />
                                    )
                                ))}
                                <text x={xCenter(last) + 6} y={yScale(vals[last]) + 3} fontSize={10} fill={TEXT_PRIMARY}>{formatNumber(vals[last])}</text>
                            </g>
                        );
                    }
                    return (
                        <g key={s}>
                            {vals.map((v, i) => {
                                const x = xCenter(i) - groupW / 2 + s * barW + 1;
                                const y = yScale(v);
                                const h = Math.max(0, pad.t + plotH - y);
                                const r = Math.min(4, barW / 2, h);
                                const w = Math.max(1, barW - 2);
                                const path = `M${x},${y + r} a${r},${r} 0 0 1 ${r},-${r} h${w - 2 * r} a${r},${r} 0 0 1 ${r},${r} v${h - r} h-${w} z`;
                                return <path key={i} d={path} fill={color} opacity={hover === null || hover === i ? 1 : 0.55} />;
                            })}
                        </g>
                    );
                })}
                {model.labels.map((_, i) => (
                    <rect key={i} x={pad.l + band * i} y={pad.t} width={band} height={plotH} fill="transparent" onMouseEnter={() => setHover(i)} />
                ))}
                {hover !== null && (
                    <line x1={xCenter(hover)} x2={xCenter(hover)} y1={pad.t} y2={pad.t + plotH} stroke={TEXT_SECONDARY} strokeWidth={1} opacity={0.5} />
                )}
            </svg>
            <div className="flex flex-wrap items-center gap-3 text-[11px]" style={{ color: TEXT_SECONDARY }}>
                {model.series.length > 1 && model.names.map((name, s) => (
                    <span key={name} className="inline-flex items-center gap-1.5">
                        <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ background: SERIES[s % SERIES.length] }} />{name}
                    </span>
                ))}
                {hover !== null && (
                    <span className="ml-auto tabular-nums" style={{ color: TEXT_PRIMARY }}>
                        {model.labels[hover]}: {model.series.map((vals, s) => `${model.names[s]} ${vals[hover].toLocaleString()}`).join(' · ')}
                    </span>
                )}
            </div>
        </div>
    );
}

export function DataBlocks({ blocks }: { blocks: AnswerBlock[] }) {
    const tables = blocks.filter((b): b is Extract<AnswerBlock, { type: 'table' }> => b.type === 'table');
    const charts = blocks.filter((b): b is Extract<AnswerBlock, { type: 'chart' }> => b.type === 'chart');
    if (!tables.length && !charts.length) return null;
    return (
        <div className="space-y-1">
            {charts.map((c, i) => {
                const table = tables.find((t) => t.data.query_id === c.data.query_id) ?? tables[0];
                return c.data.type === 'kpi'
                    ? <KpiChart key={i} data={c.data} />
                    : <SeriesChart key={i} data={c.data} table={table?.data} />;
            })}
            {tables.map((t, i) => <TableBlock key={i} data={t.data} />)}
        </div>
    );
}
