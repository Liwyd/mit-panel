/**
 * Hand-rolled SVG rings. Deliberately dependency-free: the panel installs with
 * `npm ci`, so pulling in a chart library would mean regenerating the lockfile
 * for what amounts to a few arcs.
 */

import { cn } from '@/lib/utils'

/** Palette for node segments, in the order they are handed out. */
export const SEGMENT_COLORS = [
    'hsl(var(--brand-green))',
    'hsl(var(--brand-blue))',
    'hsl(var(--brand-gold))',
    'hsl(330 65% 62%)',
    'hsl(265 60% 65%)',
    'hsl(20 80% 62%)',
]

export interface DonutSegment {
    label: string
    value: number
    color?: string
}

interface DonutProps {
    segments: DonutSegment[]
    /** Rendered in the middle of the ring. */
    centerLabel?: string
    centerCaption?: string
    size?: number
    thickness?: number
    className?: string
}

/**
 * Multi-segment ring. Segments are laid out clockwise from twelve o'clock;
 * anything below half a percent is still drawn so tiny nodes stay visible.
 */
export function Donut({
    segments,
    centerLabel,
    centerCaption,
    size = 210,
    thickness = 26,
    className,
}: DonutProps): JSX.Element {
    const radius = (size - thickness) / 2
    const circumference = 2 * Math.PI * radius
    const total = segments.reduce((sum, s) => sum + Math.max(0, s.value), 0)

    let consumed = 0

    return (
        <svg
            width={size}
            height={size}
            viewBox={`0 0 ${size} ${size}`}
            className={cn('shrink-0', className)}
            role="img"
        >
            {/* Track, also the empty state when there is nothing to show. */}
            <circle
                cx={size / 2}
                cy={size / 2}
                r={radius}
                fill="none"
                stroke="hsl(var(--muted))"
                strokeWidth={thickness}
            />

            {total > 0 &&
                segments.map((segment, index) => {
                    const share = Math.max(0, segment.value) / total
                    const length = share * circumference
                    const offset = consumed
                    consumed += length

                    return (
                        <circle
                            key={`${segment.label}-${index}`}
                            cx={size / 2}
                            cy={size / 2}
                            r={radius}
                            fill="none"
                            stroke={segment.color || SEGMENT_COLORS[index % SEGMENT_COLORS.length]}
                            strokeWidth={thickness}
                            strokeDasharray={`${length} ${circumference - length}`}
                            strokeDashoffset={-offset}
                            // Start at the top rather than at three o'clock.
                            transform={`rotate(-90 ${size / 2} ${size / 2})`}
                        >
                            <title>{`${segment.label}: ${(share * 100).toFixed(1)}%`}</title>
                        </circle>
                    )
                })}

            {centerLabel && (
                <text
                    x="50%"
                    y={centerCaption ? '47%' : '50%'}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    className="fill-foreground"
                    style={{ fontSize: size * 0.15, fontWeight: 900, letterSpacing: '-0.02em' }}
                >
                    {centerLabel}
                </text>
            )}
            {centerCaption && (
                <text
                    x="50%"
                    y="61%"
                    textAnchor="middle"
                    dominantBaseline="middle"
                    className="fill-muted-foreground"
                    style={{ fontSize: size * 0.075, fontWeight: 700 }}
                >
                    {centerCaption}
                </text>
            )}
        </svg>
    )
}

interface GaugeProps {
    /** 0 - 100. Values outside the range are clamped. */
    percent: number
    label: string
    caption?: string
    size?: number
    thickness?: number
    color?: string
    className?: string
}

/**
 * Three-quarter arc with the gap at the bottom, matching the resource dials in
 * the reference screenshots. Turns amber past 75% and red past 90%.
 */
export function Gauge({
    percent,
    label,
    caption,
    size = 132,
    thickness = 11,
    color,
    className,
}: GaugeProps): JSX.Element {
    const value = Math.min(100, Math.max(0, Number.isFinite(percent) ? percent : 0))
    const radius = (size - thickness) / 2
    const circumference = 2 * Math.PI * radius
    const arc = circumference * 0.75
    const filled = arc * (value / 100)

    const strokeColor =
        color || (value >= 90
            ? 'hsl(var(--destructive))'
            : value >= 75
                ? 'hsl(var(--brand-gold))'
                : 'hsl(var(--brand-green))')

    return (
        <div className={cn('flex flex-col items-center gap-2', className)}>
            <div className="relative" style={{ width: size, height: size }}>
                <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img">
                    <circle
                        cx={size / 2}
                        cy={size / 2}
                        r={radius}
                        fill="none"
                        stroke="hsl(var(--muted))"
                        strokeWidth={thickness}
                        strokeLinecap="round"
                        strokeDasharray={`${arc} ${circumference - arc}`}
                        // Rotate so the missing quarter sits at the bottom.
                        transform={`rotate(135 ${size / 2} ${size / 2})`}
                    />
                    <circle
                        cx={size / 2}
                        cy={size / 2}
                        r={radius}
                        fill="none"
                        stroke={strokeColor}
                        strokeWidth={thickness}
                        strokeLinecap="round"
                        strokeDasharray={`${filled} ${circumference - filled}`}
                        transform={`rotate(135 ${size / 2} ${size / 2})`}
                        style={{ transition: 'stroke-dasharray 0.5s ease, stroke 0.3s ease' }}
                    >
                        <title>{`${label}: ${value.toFixed(2)}%`}</title>
                    </circle>
                </svg>
                <div className="absolute inset-0 flex items-center justify-center">
                    <span className="text-base font-black tabular">{value.toFixed(2)}%</span>
                </div>
            </div>
            <div className="text-center leading-tight">
                <div className="text-xs font-extrabold">{label}</div>
                {caption && <div className="text-xs text-muted-foreground">{caption}</div>}
            </div>
        </div>
    )
}
