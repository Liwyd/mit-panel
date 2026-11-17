/**
 * Hand-rolled SVG column chart, dependency-free like Donut. One series: bars
 * grow from a shared baseline with a rounded top, a faint grid marks the top
 * and middle of the scale, and hovering (or tapping) a column shows its value.
 */

import { useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/utils'

export interface BarDatum {
    /** Axis label under the column. */
    label: string
    value: number
    /** Longer name for the tooltip; falls back to `label`. */
    title?: string
    /** Drawn lighter, e.g. a period that hasn't finished yet. */
    muted?: boolean
}

interface BarChartProps {
    data: BarDatum[]
    format: (value: number) => string
    /** Show every n-th axis label; the rest stay blank to avoid crowding. */
    labelEvery?: number
    height?: number
    color?: string
    className?: string
}

const PAD_TOP = 8
const PAD_BOTTOM = 22
const PAD_LEFT = 52
const GAP = 2

function columnPath(x: number, y: number, w: number, h: number): string {
    const r = Math.min(4, w / 2, h)
    if (h <= 0) return ''
    return [
        `M${x},${y + h}`,
        `V${y + r}`,
        `Q${x},${y} ${x + r},${y}`,
        `H${x + w - r}`,
        `Q${x + w},${y} ${x + w},${y + r}`,
        `V${y + h}`,
        'Z',
    ].join(' ')
}

export function BarChart({
    data,
    format,
    labelEvery = 1,
    height = 200,
    color = 'hsl(var(--brand-blue))',
    className,
}: BarChartProps): JSX.Element {
    const [active, setActive] = useState<number | null>(null)
    // Drawn at the container's real width, so text keeps its size whatever
    // the card's width instead of scaling with a fixed viewBox.
    const box = useRef<HTMLDivElement>(null)
    const [WIDTH, setWidth] = useState(640)
    useEffect(() => {
        const el = box.current
        if (!el) return
        const observer = new ResizeObserver(([entry]) => setWidth(Math.max(200, Math.round(entry.contentRect.width))))
        observer.observe(el)
        return () => observer.disconnect()
    }, [])

    const max = Math.max(0, ...data.map((d) => d.value))
    const plotH = height - PAD_TOP - PAD_BOTTOM
    const plotW = WIDTH - PAD_LEFT
    const slot = data.length ? plotW / data.length : plotW
    const barW = Math.max(2, Math.min(slot - GAP, 36))
    const baseline = PAD_TOP + plotH
    // Thin out labels further when columns get too narrow for them.
    const every = Math.max(labelEvery, Math.ceil(44 / slot))

    const hovered = active !== null ? data[active] : null
    const tipLeft = active !== null ? ((PAD_LEFT + slot * active + slot / 2) / WIDTH) * 100 : 0

    return (
        <div ref={box} dir="ltr" className={cn('relative w-full', className)} onMouseLeave={() => setActive(null)}>
            <svg
                viewBox={`0 0 ${WIDTH} ${height}`}
                // 100% rather than a fixed width, so the chart never props its card
                // open; the viewBox matches the measured width, so it draws 1:1.
                className="block w-full h-auto select-none"
                role="img"
                aria-label={data.map((d) => `${d.title ?? d.label}: ${format(d.value)}`).join(', ')}
            >
                {/* Grid: top and middle of the scale, plus the baseline. */}
                {max > 0 &&
                    [1, 0.5].map((f) => {
                        const y = PAD_TOP + plotH * (1 - f)
                        return (
                            <g key={f}>
                                <line
                                    x1={PAD_LEFT}
                                    x2={WIDTH}
                                    y1={y}
                                    y2={y}
                                    stroke="hsl(var(--border))"
                                    strokeDasharray="3 4"
                                />
                                <text
                                    x={PAD_LEFT - 8}
                                    y={y + 4}
                                    textAnchor="end"
                                    className="fill-muted-foreground"
                                    fontSize={11}
                                >
                                    {format(max * f)}
                                </text>
                            </g>
                        )
                    })}
                <line x1={PAD_LEFT} x2={WIDTH} y1={baseline} y2={baseline} stroke="hsl(var(--border))" />

                {data.map((d, i) => {
                    const h = max > 0 ? (Math.max(0, d.value) / max) * plotH : 0
                    const x = PAD_LEFT + slot * i + (slot - barW) / 2
                    const dim = active !== null && active !== i
                    return (
                        <g key={i}>
                            <path
                                d={columnPath(x, baseline - h, barW, h)}
                                fill={color}
                                opacity={(d.muted ? 0.45 : 1) * (dim ? 0.55 : 1)}
                            />
                            {i % every === 0 && (
                                <text
                                    x={x + barW / 2}
                                    y={height - 6}
                                    textAnchor="middle"
                                    className="fill-muted-foreground"
                                    fontSize={11}
                                >
                                    {d.label}
                                </text>
                            )}
                            {/* Hit area: the whole column slot, taller than the bar. */}
                            <rect
                                x={PAD_LEFT + slot * i}
                                y={PAD_TOP}
                                width={slot}
                                height={plotH}
                                fill="transparent"
                                onMouseEnter={() => setActive(i)}
                                onClick={() => setActive(i)}
                            />
                        </g>
                    )
                })}
            </svg>

            {hovered && (
                <div
                    className="pointer-events-none absolute top-0 z-10 -translate-x-1/2 whitespace-nowrap rounded-md border bg-popover px-2.5 py-1.5 text-xs shadow-md"
                    style={{ left: `clamp(60px, ${tipLeft}%, calc(100% - 60px))` }}
                >
                    <div className="text-muted-foreground">{hovered.title ?? hovered.label}</div>
                    <div className="font-semibold tabular-nums">{format(hovered.value)}</div>
                </div>
            )}
        </div>
    )
}
