import type { ReactNode } from 'react'
import { useChartTip } from './useChartTip'

/**
 * Horizontal ranked bars: a label, a thin bar growing from the start edge, the
 * value at the tip. In an RTL page the start edge is the right one, so the
 * bars read from right to left naturally. The width is relative to the
 * largest row. Each row is its own tooltip target.
 */
export interface RankedRow {
    key: string
    label: string
    value: number
    /** What is printed at the tip of the bar. */
    display: ReactNode
    /** Shown in the tooltip on hover or focus. */
    tip: ReactNode
    /** CSS colour of this bar. */
    color: string
}

export function RankedBars({ rows, ariaLabel }: { rows: RankedRow[]; ariaLabel: string }) {
    const { containerRef, bind, element } = useChartTip()
    const max = Math.max(1, ...rows.map((r) => r.value))

    return (
        <div ref={containerRef} className="relative">
            <ul className="space-y-3" aria-label={ariaLabel}>
                {rows.map((row) => (
                    <li
                        key={row.key}
                        tabIndex={0}
                        className="rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        {...bind(row.tip)}
                    >
                        <div className="pf-body flex items-baseline justify-between gap-3">
                            <span className="min-w-0">{row.label}</span>
                            <span className="shrink-0 font-bold">{row.display}</span>
                        </div>
                        <div className="mt-1.5 h-2 w-full rounded-full bg-muted-foreground/10">
                            <div
                                className="h-full rounded-full"
                                style={{
                                    width: `${row.value > 0 ? Math.max(1.5, (row.value / max) * 100) : 0}%`,
                                    background: row.color,
                                }}
                            />
                        </div>
                    </li>
                ))}
            </ul>
            {element}
        </div>
    )
}
