/**
 * Blocky resource meter: a percentage, a row of segments that fill up, and a
 * caption. Same dependency-free approach as the rings next door — this is all
 * divs, no SVG needed.
 */

import { cn } from '@/lib/utils'

const SEGMENTS = 22

/** Green until it's worth noticing, amber when it is, red when it matters. */
function levelColor(percent: number): string {
    if (percent >= 90) return 'hsl(var(--destructive))'
    if (percent >= 75) return 'hsl(var(--brand-gold))'
    return 'hsl(var(--brand-green))'
}

interface SegmentedBarProps {
    /** 0 - 100. Values outside the range are clamped. */
    percent: number
    label: string
    caption?: string
    className?: string
}

export function SegmentedBar({
    percent,
    label,
    caption,
    className,
}: SegmentedBarProps): JSX.Element {
    const value = Math.min(100, Math.max(0, Number.isFinite(percent) ? percent : 0))
    // Anything above zero lights at least one block, so a busy-but-tiny reading
    // never looks like nothing at all.
    const filled = value > 0 ? Math.max(1, Math.round((value / 100) * SEGMENTS)) : 0
    const color = levelColor(value)

    return (
        <div className={cn('min-w-0', className)}>
            <div className="flex items-baseline gap-1.5">
                <span className="text-lg font-black leading-none tabular">{value.toFixed(0)}</span>
                <span className="text-[11px] font-bold text-muted-foreground">%</span>
                <span className="truncate text-xs font-bold text-muted-foreground">{label}</span>
            </div>

            <div className="mt-1.5 flex h-5 items-stretch gap-[3px]" title={`${label}: ${value.toFixed(1)}%`}>
                {Array.from({ length: SEGMENTS }, (_, index) => (
                    <div
                        key={index}
                        className="flex-1 rounded-[2px] transition-colors"
                        style={{
                            backgroundColor: index < filled ? color : 'hsl(var(--muted-foreground) / 0.18)',
                        }}
                    />
                ))}
            </div>

            {caption && (
                <p className="mt-1.5 truncate text-[11px] text-muted-foreground">{caption}</p>
            )}
        </div>
    )
}
