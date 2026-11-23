import { useEffect, useState } from 'react'
import { profitAPI, type ProfitMonth, type ProfitReport } from '@/lib/api'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

const MONTHS = 6

const toman = (value: number) => `${Math.round(value).toLocaleString()} T`
const gb = (value: number) => `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })} GB`
const percent = (value: number | null) => (value === null ? '—' : `${(value * 100).toFixed(1)}%`)

/** "+12% vs last month", or a muted dash when last month has nothing to compare. */
function versus(current: number, previous: number | undefined): string {
    if (previous === undefined || previous === 0) return 'no data last month'
    const change = ((current - previous) / Math.abs(previous)) * 100
    const sign = change > 0 ? '+' : ''
    return `${sign}${Math.round(change)}% vs last month`
}

function marginVersus(current: number | null, previous: number | null | undefined): string {
    if (current === null || previous === null || previous === undefined) return 'no data last month'
    const points = (current - previous) * 100
    const sign = points > 0 ? '+' : ''
    return `${sign}${points.toFixed(1)} pts vs last month`
}

function Tile({
    label,
    value,
    note,
    accent,
    negative,
}: {
    label: string
    value: string
    note: string
    accent?: boolean
    negative?: boolean
}) {
    return (
        <Card>
            <CardContent className="p-4">
                <p className="text-xs font-medium text-muted-foreground">{label}</p>
                <p
                    className={cn(
                        'mt-1 text-xl font-bold tabular-nums leading-tight',
                        accent && !negative && 'text-primary',
                        negative && 'text-destructive'
                    )}
                >
                    {value}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">{note}</p>
            </CardContent>
        </Card>
    )
}

/** Revenue, cost and profit per month as grouped columns on one shared scale. */
function MonthlyBars({ months }: { months: ProfitMonth[] }) {
    // The API sends newest first; a chart reads oldest to newest.
    const ordered = [...months].reverse()
    const max = Math.max(1, ...ordered.flatMap((m) => [m.revenue, m.cost, m.profit]))
    const height = (value: number) => `${(Math.max(0, value) / max) * 100}%`

    return (
        <div>
            <div className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                <span className="flex items-center gap-1.5">
                    <i className="h-2.5 w-2.5 rounded-sm bg-muted-foreground/30" /> Revenue
                </span>
                <span className="flex items-center gap-1.5">
                    <i className="h-2.5 w-2.5 rounded-sm bg-muted-foreground/60" /> Cost
                </span>
                <span className="flex items-center gap-1.5">
                    <i className="h-2.5 w-2.5 rounded-sm bg-primary" /> Profit
                </span>
            </div>
            <div className="flex h-44 items-end gap-2 border-b border-border">
                {ordered.map((m) => (
                    <div
                        key={m.key}
                        className="flex h-full min-w-0 flex-1 items-end justify-center gap-0.5 sm:gap-1"
                        title={`${m.label_fa}\nRevenue ${toman(m.revenue)}\nCost ${toman(m.cost)}\nProfit ${toman(m.profit)}`}
                    >
                        <div className="w-full max-w-[18px] rounded-t bg-muted-foreground/30" style={{ height: height(m.revenue) }} />
                        <div className="w-full max-w-[18px] rounded-t bg-muted-foreground/60" style={{ height: height(m.cost) }} />
                        <div className="w-full max-w-[18px] rounded-t bg-primary" style={{ height: height(m.profit) }} />
                    </div>
                ))}
            </div>
            <div className="mt-1.5 flex gap-2">
                {ordered.map((m) => (
                    <div key={m.key} className="min-w-0 flex-1 truncate text-center text-[11px] text-muted-foreground" dir="rtl">
                        {m.label_fa.split(' ')[0]}
                    </div>
                ))}
            </div>
        </div>
    )
}

export function ProfitSection() {
    const [report, setReport] = useState<ProfitReport | null>(null)
    const [failed, setFailed] = useState(false)
    const [selected, setSelected] = useState<string | null>(null)

    useEffect(() => {
        let cancelled = false
        profitAPI
            .get(MONTHS)
            .then((data) => {
                if (!cancelled) setReport(data)
            })
            .catch(() => {
                if (!cancelled) setFailed(true)
            })
        return () => {
            cancelled = true
        }
    }, [])

    const months = report?.months ?? []
    const current = months[0]
    const previous = months[1]
    const month = months.find((m) => m.key === (selected ?? current?.key)) ?? current

    if (failed) {
        return <p className="text-sm text-muted-foreground">The profit report is unavailable right now.</p>
    }
    if (!report || !current || !month) return null

    const bf = report.black_friday
    const showBf = bf.active || bf.purchases > 0 || bf.settlements > 0

    return (
        <div className="space-y-4">
            <div className="flex items-baseline justify-between gap-3">
                <h2 className="text-lg font-bold">Profit</h2>
                <span className="text-xs text-muted-foreground">
                    {current.label_fa} · cost {toman(report.cost_per_gb)}/GB
                </span>
            </div>

            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <Tile label="Revenue" value={toman(current.revenue)} note={versus(current.revenue, previous?.revenue)} />
                <Tile label="Cost" value={toman(current.cost)} note={versus(current.cost, previous?.cost)} />
                <Tile
                    label="Profit"
                    value={toman(current.profit)}
                    note={versus(current.profit, previous?.profit)}
                    accent
                    negative={current.profit < 0}
                />
                <Tile label="Margin" value={percent(current.margin)} note={marginVersus(current.margin, previous?.margin)} />
            </div>

            <Card>
                <CardHeader className="pb-2">
                    <CardTitle className="text-base">Last {months.length} months</CardTitle>
                </CardHeader>
                <CardContent>
                    <MonthlyBars months={months} />
                </CardContent>
            </Card>

            <Card>
                <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <CardTitle className="text-base">By panel</CardTitle>
                    <Select value={month.key} onValueChange={setSelected}>
                        <SelectTrigger className="w-full sm:w-48" aria-label="Month">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            {months.map((m) => (
                                <SelectItem key={m.key} value={m.key}>
                                    {m.label_fa}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </CardHeader>
                <CardContent className="space-y-3">
                    {month.per_admin.length === 0 ? (
                        <p className="text-sm text-muted-foreground">No sales in this month.</p>
                    ) : (
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Panel</TableHead>
                                    <TableHead className="text-right">GB sold</TableHead>
                                    <TableHead className="text-right">Avg price/GB</TableHead>
                                    <TableHead className="text-right">Revenue</TableHead>
                                    <TableHead className="text-right">Cost</TableHead>
                                    <TableHead className="text-right">Profit</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {month.per_admin.map((row) => (
                                    <TableRow key={row.username}>
                                        <TableCell className="font-medium whitespace-nowrap">{row.username}</TableCell>
                                        <TableCell className="text-right tabular-nums whitespace-nowrap">{gb(row.gb_sold)}</TableCell>
                                        <TableCell className="text-right tabular-nums whitespace-nowrap">
                                            {row.avg_price_per_gb === null ? '—' : toman(row.avg_price_per_gb)}
                                        </TableCell>
                                        <TableCell className="text-right tabular-nums whitespace-nowrap">{toman(row.revenue)}</TableCell>
                                        <TableCell className="text-right tabular-nums whitespace-nowrap">{toman(row.cost)}</TableCell>
                                        <TableCell
                                            className={cn(
                                                'text-right tabular-nums whitespace-nowrap font-medium',
                                                row.profit < 0 && 'text-destructive'
                                            )}
                                        >
                                            {toman(row.profit)}
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    )}
                    {month.unknown_gb_revenue > 0 && (
                        <p className="text-xs text-muted-foreground">
                            {toman(month.unknown_gb_revenue)} of this month's payments have no GB recorded, so their
                            cost is not counted.
                        </p>
                    )}
                </CardContent>
            </Card>

            {showBf && (
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-base">
                            Black Friday{bf.active ? '' : ' (ended)'}
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm sm:grid-cols-3">
                            {[
                                ['Purchases', `${bf.purchases.toLocaleString()} from ${bf.buyers.toLocaleString()} buyers`],
                                ['GB paid + gift', `${gb(bf.paid_gb)} + ${gb(bf.gift_gb)}`],
                                [
                                    'Money taken',
                                    `${toman(bf.card_amount + bf.wallet_amount)} (card ${toman(bf.card_amount)}, wallet ${toman(bf.wallet_amount)})`,
                                ],
                                ['Discount given', toman(bf.discount + bf.settlements_discount)],
                                ['Cost of GB', toman(bf.cost)],
                            ].map(([label, value]) => (
                                <div key={label}>
                                    <dt className="text-xs text-muted-foreground">{label}</dt>
                                    <dd className="tabular-nums">{value}</dd>
                                </div>
                            ))}
                            <div>
                                <dt className="text-xs text-muted-foreground">Event profit</dt>
                                <dd className={cn('font-bold tabular-nums', bf.profit < 0 ? 'text-destructive' : 'text-primary')}>
                                    {toman(bf.profit)}
                                </dd>
                            </div>
                        </dl>
                    </CardContent>
                </Card>
            )}
        </div>
    )
}
