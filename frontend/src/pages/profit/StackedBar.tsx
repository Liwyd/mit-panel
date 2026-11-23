import type { ReactNode } from 'react'
import { useChartTip } from './useChartTip'
import { faPercent } from './format'

/**
 * One whole split into parts: a tall segmented bar. Widths follow the values,
 * a 2px surface gap separates the parts, a part at zero draws nothing, and a
 * part's share is printed inside it only when the text fits (wider than 14%);
 * every part's name and amount are in the legend and the tooltip.
 */
export interface StackPart {
    key: string
    label: string
    value: number
    /** Which ordinal step (1-5) fills this part. */
    step: 1 | 2 | 3 | 4 | 5
    /** Shown in the tooltip and beside the name in the legend. */
    detail: ReactNode
}

export function StackedBar({ parts, ariaLabel }: { parts: StackPart[]; ariaLabel: string }) {
    const { containerRef, bind, element } = useChartTip()
    const total = parts.reduce((sum, p) => sum + p.value, 0)

    return (
        <div ref={containerRef} className="relative">
            {total > 0 ? (
                <div className="flex h-7 w-full gap-0.5" role="img" aria-label={ariaLabel}>
                    {parts
                        .filter((p) => p.value > 0)
                        .map((p) => {
                            const share = p.value / total
                            return (
                                <div
                                    key={p.key}
                                    tabIndex={0}
                                    className="flex min-w-[4px] items-center overflow-hidden rounded px-2 text-[11px] font-bold leading-none outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                    style={{
                                        flexGrow: p.value,
                                        flexBasis: 0,
                                        background: `var(--pf-o${p.step})`,
                                        color: `var(--pf-o${p.step}-ink)`,
                                    }}
                                    {...bind(
                                        <div className="pf-caption">
                                            <div className="font-bold text-foreground">{p.label}</div>
                                            <div>{p.detail}</div>
                                            <div className="text-muted-foreground">{faPercent(share)}</div>
                                        </div>
                                    )}
                                >
                                    {share >= 0.14 ? faPercent(share) : null}
                                </div>
                            )
                        })}
                </div>
            ) : (
                <div className="h-7 w-full rounded bg-muted-foreground/10" role="img" aria-label={ariaLabel} />
            )}
            <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1">
                {parts.map((p) => (
                    <li key={p.key} className="pf-caption flex items-center gap-2 text-muted-foreground">
                        <i className="inline-block h-2.5 w-2.5 rounded-[3px]" style={{ background: `var(--pf-o${p.step})` }} />
                        <span>{p.label}</span>
                        <span className="font-bold text-foreground">{p.detail}</span>
                    </li>
                ))}
            </ul>
            {element}
        </div>
    )
}
