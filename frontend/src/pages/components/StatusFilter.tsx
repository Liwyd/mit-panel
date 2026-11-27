/**
 * Segmented status filter for the user list: every status with its count,
 * and a pill that slides to the selected one on a spring.
 */
import { useLayoutEffect, useRef } from 'react'
import { animated, useReducedMotion, useSpring } from '@react-spring/web'
import { cn } from '@/lib/utils'

export type UserStatusFilter = 'all' | 'online' | 'active' | 'inactive'

const OPTIONS: { value: UserStatusFilter; label: string; dot?: string }[] = [
    { value: 'all', label: 'All' },
    { value: 'online', label: 'Online', dot: 'bg-emerald-500' },
    { value: 'active', label: 'Active', dot: 'bg-foreground/40' },
    { value: 'inactive', label: 'Inactive', dot: 'bg-destructive' },
]

export function StatusFilter({
    value,
    counts,
    onChange,
}: {
    value: UserStatusFilter
    counts: Record<UserStatusFilter, number>
    onChange: (value: UserStatusFilter) => void
}) {
    const reduced = !!useReducedMotion()
    const trackRef = useRef<HTMLDivElement>(null)
    const buttons = useRef<Partial<Record<UserStatusFilter, HTMLButtonElement | null>>>({})
    const [pill, api] = useSpring(() => ({ x: 0, w: 0, opacity: 0, config: { tension: 420, friction: 34 } }))

    // Follow the selected button, also when the track resizes (fonts, viewport).
    useLayoutEffect(() => {
        const track = trackRef.current
        if (!track) return
        let first = true
        const place = () => {
            const el = buttons.current[value]
            if (!el) return
            api.start({ x: el.offsetLeft, w: el.offsetWidth, opacity: 1, immediate: first || reduced })
            first = false
        }
        place()
        const ro = new ResizeObserver(place)
        ro.observe(track)
        return () => ro.disconnect()
    }, [value, reduced, api])

    return (
        <div
            ref={trackRef}
            role="radiogroup"
            aria-label="Filter users by status"
            className="relative grid w-full grid-cols-4 rounded-xl border border-border/70 bg-muted/50 p-1 sm:flex sm:w-auto"
        >
            <animated.span
                aria-hidden
                className="absolute bottom-1 left-0 top-1 rounded-lg bg-card shadow-[0_1px_2px_rgba(0,0,0,0.06),0_6px_16px_-8px_rgba(0,0,0,0.25)] ring-1 ring-border/60"
                style={{ width: pill.w, opacity: pill.opacity, transform: pill.x.to((x) => `translateX(${x}px)`) }}
            />
            {OPTIONS.map((o) => {
                const selected = o.value === value
                return (
                    <button
                        key={o.value}
                        ref={(el) => {
                            buttons.current[o.value] = el
                        }}
                        type="button"
                        role="radio"
                        aria-checked={selected}
                        onClick={() => onChange(o.value)}
                        className={cn(
                            'relative z-10 inline-flex h-8 min-w-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-lg px-1.5 text-xs font-medium transition-colors duration-200 sm:gap-2 sm:px-3',
                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                            selected ? 'text-foreground' : 'text-muted-foreground hover:text-foreground',
                        )}
                    >
                        {o.dot && <span className={cn('hidden h-1.5 w-1.5 rounded-full sm:inline-block', o.dot)} />}
                        {o.label}
                        <span
                            className={cn(
                                'min-w-[1.25rem] rounded-full px-1.5 py-px text-[10px] tabular-nums transition-colors',
                                selected ? 'bg-foreground/[0.07] text-foreground' : 'bg-transparent text-muted-foreground/80',
                            )}
                        >
                            {counts[o.value]}
                        </span>
                    </button>
                )
            })}
        </div>
    )
}
