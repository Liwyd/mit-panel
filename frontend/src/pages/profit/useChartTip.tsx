import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from 'react'
import { cn } from '@/lib/utils'

/**
 * One tooltip per chart. The chart container is `position: relative`; the tip
 * is placed from the pointer (or the focused mark) and clamped inside it. It
 * fades in and out over 150ms. Touch has no hover, so a tap shows it and a tap
 * anywhere else hides it.
 */
interface TipState {
    x: number
    y: number
    node: ReactNode
}

export function useChartTip() {
    const containerRef = useRef<HTMLDivElement>(null)
    const [tip, setTip] = useState<TipState | null>(null)
    const [visible, setVisible] = useState(false)

    const place = useCallback((clientX: number, clientY: number, node: ReactNode) => {
        const box = containerRef.current?.getBoundingClientRect()
        if (!box) return
        setTip({ x: clientX - box.left, y: clientY - box.top, node })
        setVisible(true)
    }, [])

    const hide = useCallback(() => setVisible(false), [])

    useEffect(() => {
        if (!visible) return
        const outside = (event: PointerEvent) => {
            if (!containerRef.current?.contains(event.target as Node)) setVisible(false)
        }
        document.addEventListener('pointerdown', outside)
        return () => document.removeEventListener('pointerdown', outside)
    }, [visible])

    /** Handlers to spread on a mark: hover, focus and tap all show the same tip. */
    const bind = useCallback(
        (node: ReactNode) => ({
            onPointerEnter: (e: React.PointerEvent) => place(e.clientX, e.clientY, node),
            onPointerMove: (e: React.PointerEvent) => place(e.clientX, e.clientY, node),
            onPointerLeave: (e: React.PointerEvent) => {
                if (e.pointerType === 'mouse') hide()
            },
            onClick: (e: React.MouseEvent) => place(e.clientX, e.clientY, node),
            onFocus: (e: React.FocusEvent) => {
                const box = e.currentTarget.getBoundingClientRect()
                place(box.left + box.width / 2, box.top + box.height / 2, node)
            },
            onBlur: hide,
        }),
        [place, hide]
    )

    const element = <TipBox containerRef={containerRef} tip={tip} visible={visible} />
    return { containerRef, bind, element }
}

function TipBox({
    containerRef,
    tip,
    visible,
}: {
    containerRef: RefObject<HTMLDivElement>
    tip: TipState | null
    visible: boolean
}) {
    const boxRef = useRef<HTMLDivElement>(null)
    const [pos, setPos] = useState({ left: 0, top: 0 })

    useLayoutEffect(() => {
        const box = boxRef.current
        const container = containerRef.current
        if (!tip || !box || !container) return
        const width = box.offsetWidth
        const height = box.offsetHeight
        const bounds = container.getBoundingClientRect()
        const left = Math.min(Math.max(tip.x - width / 2, 0), Math.max(0, bounds.width - width))
        // Above the pointer when there is room, else below it.
        const above = tip.y - height - 14
        setPos({ left, top: above >= 0 ? above : tip.y + 18 })
    }, [tip, containerRef])

    if (!tip) return null
    return (
        <div
            ref={boxRef}
            role="tooltip"
            dir="rtl"
            style={{ left: pos.left, top: pos.top }}
            className={cn(
                'pf-tip pointer-events-none absolute z-20 w-max max-w-[16rem] rounded-lg border border-border bg-popover px-3 py-2 text-popover-foreground shadow-lg',
                visible ? 'opacity-100' : 'opacity-0'
            )}
        >
            {tip.node}
        </div>
    )
}

/** A tooltip row: a short stroke in the series colour, the name, the value
    leading. The value is the strong element; the name is secondary. */
export function TipRow({ color, label, value }: { color?: string; label: string; value: ReactNode }) {
    return (
        <div className="pf-caption flex items-center justify-between gap-4">
            <span className="flex items-center gap-2 text-muted-foreground">
                {color && <i className="inline-block h-0.5 w-3 shrink-0 rounded-full" style={{ background: color }} />}
                {label}
            </span>
            <span className="font-bold tabular-nums text-foreground" dir="ltr">
                {value}
            </span>
        </div>
    )
}

export function TipTitle({ children }: { children: ReactNode }) {
    return <div className="pf-caption mb-1 font-bold text-foreground">{children}</div>
}
