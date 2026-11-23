import { useMemo, useRef } from 'react'
import type { ProfitMonth } from '@/lib/api'
import { axisScale, fa, monthName, monthYear, tickLabel } from './format'
import { useElementWidth } from './useElementWidth'
import { TipRow, TipTitle, useChartTip } from './useChartTip'
import { Money, Num } from './parts'

/**
 * Revenue, cost and net profit per month on ONE toman axis; a negative value is
 * drawn below the zero line instead of being clamped.
 *
 * Direction: the page is RTL, but a time axis is drawn left-to-right (oldest on
 * the left) inside this chart on purpose: `dir="ltr"` on the SVG keeps one
 * consistent reading order for every chart on the page, with Persian month
 * labels. Cost here is everything the month cost: GB cost plus fixed cost, so
 * revenue - cost = net profit.
 */
const SERIES = [
    { key: 'revenue', label: 'درآمد', color: 'var(--pf-s1)' },
    { key: 'cost', label: 'هزینه', color: 'var(--pf-s2)' },
    { key: 'net', label: 'سود خالص', color: 'var(--pf-s3)' },
] as const

const HEIGHT = 300
const PAD = { top: 12, right: 8, bottom: 44, left: 36 }
const MIN_SLOT = 22
const BAR_MAX = 18
const BAR_GAP = 2

/** A bar from the baseline to a value, with the 4px rounding only on the data end. */
function barPath(x: number, base: number, end: number, width: number): string {
    const r = Math.min(4, width / 2, Math.abs(end - base))
    if (Math.abs(end - base) < 0.5) return ''
    if (end < base) {
        return `M${x},${base} V${end + r} Q${x},${end} ${x + r},${end} H${x + width - r} Q${x + width},${end} ${x + width},${end + r} V${base} Z`
    }
    return `M${x},${base} V${end - r} Q${x},${end} ${x + r},${end} H${x + width - r} Q${x + width},${end} ${x + width},${end - r} V${base} Z`
}

export function MainChart({
    months,
    selectedKey,
    onSelect,
}: {
    months: ProfitMonth[]
    selectedKey: string
    onSelect: (key: string) => void
}) {
    const wrapRef = useRef<HTMLDivElement>(null)
    const available = useElementWidth(wrapRef)
    const { containerRef, bind, element } = useChartTip()
    // The API sends newest first; a time axis reads oldest to newest.
    const ordered = useMemo(() => [...months].reverse(), [months])
    const rows = useMemo(
        () =>
            ordered.map((m) => ({
                m,
                revenue: m.revenue,
                cost: m.cost + m.fixed_cost,
                net: m.net_profit,
            })),
        [ordered]
    )
    const scale = useMemo(
        () => axisScale(Math.min(0, ...rows.map((r) => r.net)), Math.max(1, ...rows.map((r) => Math.max(r.revenue, r.cost, r.net)))),
        [rows]
    )

    const width = Math.max(available, PAD.left + PAD.right + rows.length * MIN_SLOT)
    const plotW = width - PAD.left - PAD.right
    const plotH = HEIGHT - PAD.top - PAD.bottom
    const slot = plotW / rows.length
    const slotPad = slot < 36 ? 4 : 12
    const barW = Math.min(BAR_MAX, (slot - slotPad - BAR_GAP * 2) / 3)
    // Month names need ~52px each: on a narrow chart only every n-th is named.
    const stride = Math.max(1, Math.ceil(52 / slot))
    const y = (value: number) => PAD.top + (1 - (value - scale.min) / (scale.max - scale.min)) * plotH
    const zero = y(0)

    return (
        <div ref={containerRef} className="relative">
            <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-1">
                {SERIES.map((s) => (
                    <span key={s.key} className="pf-caption flex items-center gap-2 text-muted-foreground">
                        <i className="inline-block h-2.5 w-2.5 rounded-[3px]" style={{ background: s.color }} />
                        {s.label}
                    </span>
                ))}
                <span className="pf-caption ms-auto text-muted-foreground">{scale.unit}</span>
            </div>
            <div ref={wrapRef} className="overflow-x-auto">
                <svg
                    style={{ direction: 'ltr' }}
                    width={width}
                    height={HEIGHT}
                    role="img"
                    aria-label="نمودار درآمد، هزینه و سود خالص ماهانه"
                    className="block max-w-none"
                >
                    {scale.ticks.map((t) => (
                        <g key={t}>
                            <line
                                x1={PAD.left}
                                x2={width - PAD.right}
                                y1={y(t)}
                                y2={y(t)}
                                stroke="hsl(var(--border))"
                                strokeWidth={1}
                            />
                            <text
                                x={PAD.left - 8}
                                y={y(t)}
                                textAnchor="end"
                                dominantBaseline="middle"
                                fontSize={11}
                                fill="hsl(var(--muted-foreground))"
                            >
                                {tickLabel(t, scale.divisor)}
                            </text>
                        </g>
                    ))}
                    <line
                        x1={PAD.left}
                        x2={width - PAD.right}
                        y1={zero}
                        y2={zero}
                        stroke="hsl(var(--muted-foreground) / 0.45)"
                        strokeWidth={1}
                    />
                    {rows.map((row, i) => {
                        const x0 = PAD.left + i * slot
                        const groupW = barW * 3 + BAR_GAP * 2
                        const gx = x0 + (slot - groupW) / 2
                        const selected = row.m.key === selectedKey
                        const showYear = i === 0 || row.m.key.endsWith('-01')
                        const tipNode = (
                            <div>
                                <TipTitle>{row.m.label_fa}</TipTitle>
                                <TipRow color="var(--pf-s1)" label="درآمد" value={<Money value={row.revenue} />} />
                                <TipRow color="var(--pf-s2)" label="هزینه" value={<Money value={row.cost} />} />
                                {row.m.fixed_cost > 0 && (
                                    <div className="pf-caption text-muted-foreground">
                                        شامل <Num>{fa(row.m.fixed_cost)}</Num> هزینه ثابت
                                    </div>
                                )}
                                <TipRow color="var(--pf-s3)" label="سود خالص" value={<Money value={row.net} />} />
                            </div>
                        )
                        return (
                            <g key={row.m.key}>
                                {selected && (
                                    <rect
                                        x={x0 + 2}
                                        y={PAD.top}
                                        width={slot - 4}
                                        height={plotH}
                                        rx={6}
                                        fill="hsl(var(--muted-foreground) / 0.1)"
                                    />
                                )}
                                {SERIES.map((s, j) => {
                                    const value = row[s.key]
                                    return (
                                        <path
                                            key={s.key}
                                            d={barPath(gx + j * (barW + BAR_GAP), zero, y(value), barW)}
                                            fill={s.color}
                                        />
                                    )
                                })}
                                {(rows.length - 1 - i) % stride === 0 && (
                                <text
                                    x={x0 + slot / 2}
                                    y={HEIGHT - PAD.bottom + 18}
                                    textAnchor="middle"
                                    fontSize={11}
                                    fontWeight={selected ? 700 : 400}
                                    fill={selected ? 'hsl(var(--foreground))' : 'hsl(var(--muted-foreground))'}
                                >
                                    {monthName(row.m.key)}
                                </text>
                                )}
                                {showYear && (rows.length - 1 - i) % stride === 0 && (
                                    <text
                                        x={x0 + slot / 2}
                                        y={HEIGHT - PAD.bottom + 34}
                                        textAnchor="middle"
                                        fontSize={10}
                                        fill="hsl(var(--muted-foreground))"
                                    >
                                        {monthYear(row.m.key)}
                                    </text>
                                )}
                                {/* The hit target is the whole month column, not the painted bars. */}
                                <rect
                                    x={x0}
                                    y={PAD.top}
                                    width={slot}
                                    height={plotH + PAD.bottom - 8}
                                    fill="transparent"
                                    tabIndex={0}
                                    role="button"
                                    aria-label={`${row.m.label_fa}: درآمد ${fa(row.revenue)}، هزینه ${fa(row.cost)}، سود خالص ${fa(row.net)} تومان`}
                                    className="cursor-pointer outline-none focus-visible:stroke-[hsl(var(--ring))] focus-visible:[stroke-width:2px]"
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter' || e.key === ' ') {
                                            e.preventDefault()
                                            onSelect(row.m.key)
                                        }
                                    }}
                                    {...bind(tipNode)}
                                    onClick={(e) => {
                                        onSelect(row.m.key)
                                        bind(tipNode).onClick(e)
                                    }}
                                />
                            </g>
                        )
                    })}
                </svg>
            </div>
            {element}
        </div>
    )
}
