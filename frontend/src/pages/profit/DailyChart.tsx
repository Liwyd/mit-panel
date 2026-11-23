import { useMemo, useRef } from 'react'
import type { ProfitDay } from '@/lib/api'
import { axisScale, fa, faDec, monthName, tickLabel } from './format'
import { useElementWidth } from './useElementWidth'
import { TipRow, TipTitle, useChartTip } from './useChartTip'
import { Gb, Money } from './parts'

/**
 * Revenue per day of the selected month: one thin bar a day, days that have not
 * happened yet left empty, and a dashed line at the average of the days so far.
 * Time runs left to right (dir="ltr" on the SVG), like every chart on the page.
 */
const HEIGHT = 240
const PAD = { top: 12, right: 8, bottom: 28, left: 40 }

export function DailyChart({ days, monthKey }: { days: ProfitDay[]; monthKey: string }) {
    const wrapRef = useRef<HTMLDivElement>(null)
    const width = useElementWidth(wrapRef)
    const { containerRef, bind, element } = useChartTip()

    const past = useMemo(() => days.filter((d) => !d.future), [days])
    const average = past.length ? past.reduce((sum, d) => sum + d.revenue, 0) / past.length : 0
    const scale = useMemo(
        () => axisScale(Math.min(0, ...days.map((d) => d.revenue)), Math.max(1, ...days.map((d) => d.revenue)), 5),
        [days]
    )

    const plotW = width - PAD.left - PAD.right
    const plotH = HEIGHT - PAD.top - PAD.bottom
    const slot = plotW / days.length
    const barW = Math.max(2, Math.min(14, slot - 4))
    const y = (value: number) => PAD.top + (1 - (value - scale.min) / (scale.max - scale.min)) * plotH
    const zero = y(0)
    const month = monthName(monthKey)

    return (
        <div ref={containerRef} className="relative">
            <p className="pf-caption mb-2 text-muted-foreground">{scale.unit}</p>
            <div ref={wrapRef}>
                <svg
                    style={{ direction: 'ltr' }}
                    width={width}
                    height={HEIGHT}
                    role="img"
                    aria-label={`درآمد روزانه ${month}`}
                    className="block"
                >
                    {scale.ticks.map((t) => (
                        <g key={t}>
                            <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} stroke="hsl(var(--border))" />
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
                    <line x1={PAD.left} x2={width - PAD.right} y1={zero} y2={zero} stroke="hsl(var(--muted-foreground) / 0.45)" />
                    {days.map((d, i) => {
                        const x0 = PAD.left + i * slot
                        const x = x0 + (slot - barW) / 2
                        const top = y(d.revenue)
                        const showLabel = d.day === 1 || d.day % 5 === 0
                        const tipNode = (
                            <div>
                                <TipTitle>
                                    {fa(d.day)} {month}
                                </TipTitle>
                                <TipRow color="var(--pf-s1)" label="درآمد" value={<Money value={d.revenue} />} />
                                <TipRow label="فروش" value={<Gb value={d.gb_sold} />} />
                            </div>
                        )
                        return (
                            <g key={d.day}>
                                {!d.future && Math.abs(top - zero) >= 0.5 && (
                                    <rect
                                        x={x}
                                        y={Math.min(top, zero)}
                                        width={barW}
                                        height={Math.abs(top - zero)}
                                        rx={Math.min(3, barW / 2)}
                                        fill="var(--pf-s1)"
                                    />
                                )}
                                {showLabel && (
                                    <text
                                        x={x0 + slot / 2}
                                        y={HEIGHT - 8}
                                        textAnchor="middle"
                                        fontSize={11}
                                        fill="hsl(var(--muted-foreground))"
                                    >
                                        {fa(d.day)}
                                    </text>
                                )}
                                {!d.future && (
                                    <rect
                                        x={x0}
                                        y={PAD.top}
                                        width={slot}
                                        height={plotH}
                                        fill="transparent"
                                        tabIndex={0}
                                        aria-label={`${fa(d.day)} ${month}: ${fa(d.revenue)} تومان`}
                                        className="outline-none focus-visible:stroke-[hsl(var(--ring))] focus-visible:[stroke-width:2px]"
                                        {...bind(tipNode)}
                                    />
                                )}
                            </g>
                        )
                    })}
                    {average > 0 && (
                        <g pointerEvents="none">
                            <line
                                x1={PAD.left}
                                x2={width - PAD.right}
                                y1={y(average)}
                                y2={y(average)}
                                stroke="hsl(var(--foreground) / 0.55)"
                                strokeWidth={1}
                                strokeDasharray="4 4"
                            />
                        </g>
                    )}
                </svg>
            </div>
            <p className="pf-caption mt-1 flex items-center gap-2 text-muted-foreground">
                <svg width="18" height="2" aria-hidden style={{ direction: 'ltr' }}>
                    <line x1="0" x2="18" y1="1" y2="1" stroke="hsl(var(--foreground) / 0.55)" strokeDasharray="4 4" />
                </svg>
                میانگین روزانه: <span className="font-bold text-foreground">{faDec(average / scale.divisor)}</span>{' '}
                {scale.unit}
            </p>
            {element}
        </div>
    )
}
