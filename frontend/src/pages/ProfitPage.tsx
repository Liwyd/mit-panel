import { useCallback, useEffect, useState } from 'react'
import { SlidersHorizontal, Table2, BarChart3 } from 'lucide-react'
import { profitAPI, type ProfitOverview } from '@/lib/api'
import { PageLayout } from '@/components/PageLayout'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { fa, faPercent } from './profit/format'
import { MainChart } from './profit/MainChart'
import { DailyChart } from './profit/DailyChart'
import { PanelTable } from './profit/PanelTable'
import { SettingsDialog } from './profit/SettingsDialog'
import { Num, Quiet, SectionCard, SkeletonCard } from './profit/parts'
import {
    BlackFridayCard,
    CustomersCard,
    KpiTiles,
    MethodsCard,
    PriceBandsCard,
    ReceivablesCard,
    TargetCard,
    UnitEconomicsCard,
    UnknownGbNote,
} from './profit/Sections'

const RANGES = [
    { months: 6, label: '۶ ماه' },
    { months: 12, label: '۱۲ ماه' },
] as const

interface Loaded {
    key: string
    data?: ProfitOverview
    failed?: boolean
}

export function ProfitPage() {
    const [range, setRange] = useState<6 | 12>(12)
    const [monthKey, setMonthKey] = useState<string | null>(null)
    const [reload, setReload] = useState(0)
    const [loaded, setLoaded] = useState<Loaded | null>(null)
    const [lastGood, setLastGood] = useState<ProfitOverview | null>(null)
    const [settingsOpen, setSettingsOpen] = useState(false)
    const [showTable, setShowTable] = useState(false)

    const requestKey = `${range}|${monthKey ?? ''}|${reload}`
    useEffect(() => {
        let cancelled = false
        profitAPI
            .overview(range, monthKey)
            .then((data) => {
                if (cancelled) return
                setLastGood(data)
                setLoaded({ key: requestKey, data })
            })
            .catch(() => {
                if (!cancelled) setLoaded({ key: requestKey, failed: true })
            })
        return () => {
            cancelled = true
        }
    }, [range, monthKey, requestKey])

    const loading = loaded?.key !== requestKey
    // While a new slice loads, the previous render stays on screen, dimmed.
    const data = lastGood
    const failedWhole = loaded?.key === requestKey && loaded.failed === true && lastGood === null

    const months = data?.months ?? null
    const selected = data?.selected ?? null
    const settings = data?.settings ?? null
    const activeKey = selected?.key ?? monthKey ?? months?.[0]?.key ?? ''

    const chooseRange = useCallback(
        (next: 6 | 12) => {
            // A month older than the shorter range is no longer on offer.
            if (monthKey && months) {
                const index = months.findIndex((m) => m.key === monthKey)
                if (index >= next) setMonthKey(null)
            }
            setRange(next)
        },
        [monthKey, months]
    )

    const refresh = () => setReload((n) => n + 1)

    if (failedWhole) {
        return (
            <PageLayout>
                <div dir="rtl" lang="fa" className="profit-page p-4 md:p-6">
                    <SectionCard title="محاسبه سود">
                        <Quiet>بارگذاری اطلاعات سود انجام نشد.</Quiet>
                        <div className="flex justify-center">
                            <Button variant="outline" onClick={refresh}>
                                تلاش دوباره
                            </Button>
                        </div>
                    </SectionCard>
                </div>
            </PageLayout>
        )
    }

    const rangeMonths = months?.length ?? range
    const initial = data === null

    return (
        <PageLayout>
            <div dir="rtl" lang="fa" className="profit-page mx-auto w-full max-w-[1400px] space-y-5 p-4 md:space-y-6 md:p-6">
                {/* Filters: one row above everything they scope. */}
                <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
                    <div>
                        <h1 className="text-2xl font-black tracking-normal md:text-3xl">محاسبه سود</h1>
                        <p className="pf-body text-muted-foreground">
                            درآمد، هزینه و سود کسب‌وکار، بر پایه‌ی دفتر فروش
                        </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 sm:gap-3">
                        <Select value={activeKey} onValueChange={(v) => setMonthKey(v)} disabled={!months} dir="rtl">
                            <SelectTrigger className="w-40" aria-label="ماه">
                                <SelectValue placeholder="ماه" />
                            </SelectTrigger>
                            <SelectContent dir="rtl">
                                {(months ?? []).map((m) => (
                                    <SelectItem key={m.key} value={m.key}>
                                        {m.label_fa}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        <div
                            role="group"
                            aria-label="بازه‌ی نمودار"
                            className="flex h-11 rounded-lg border border-input bg-card p-1"
                        >
                            {RANGES.map((r) => (
                                <button
                                    key={r.months}
                                    type="button"
                                    aria-pressed={range === r.months}
                                    onClick={() => chooseRange(r.months)}
                                    className={cn(
                                        'pf-body rounded-md px-3.5 font-bold transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                                        range === r.months
                                            ? 'bg-muted text-foreground'
                                            : 'text-muted-foreground hover:text-foreground'
                                    )}
                                >
                                    {r.label}
                                </button>
                            ))}
                        </div>
                        <Button variant="outline" onClick={() => setSettingsOpen(true)} disabled={!settings} className="gap-2">
                            <SlidersHorizontal className="h-4 w-4" />
                            تنظیمات محاسبه
                        </Button>
                    </div>
                </div>

                <div className={cn('space-y-5 transition-opacity duration-150 md:space-y-6', loading && !initial && 'opacity-60')}>
                    {initial ? (
                        <Skeletons />
                    ) : (
                        <>
                            {/* 2. KPI tiles */}
                            {selected ? (
                                <>
                                    <KpiTiles s={selected} />
                                    <UnknownGbNote s={selected} />
                                </>
                            ) : (
                                <SectionCard title="شاخص‌های ماه">
                                    <Quiet />
                                </SectionCard>
                            )}

                            {/* 3. Target and forecast */}
                            {selected && settings && (selected.target || selected.forecast) && (
                                <TargetCard s={selected} settings={settings} />
                            )}

                            {/* 4. Main chart */}
                            <SectionCard
                                title="روند ماهانه"
                                subtitle={`درآمد، هزینه و سود خالص در ${fa(rangeMonths)} ماه اخیر`}
                                action={
                                    months && (
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            onClick={() => setShowTable((v) => !v)}
                                            className="gap-2 text-muted-foreground"
                                        >
                                            {showTable ? <BarChart3 className="h-4 w-4" /> : <Table2 className="h-4 w-4" />}
                                            {showTable ? 'نمایش نمودار' : 'نمایش جدول'}
                                        </Button>
                                    )
                                }
                            >
                                {months === null ? (
                                    <Quiet />
                                ) : showTable ? (
                                    <MonthsTable months={months} />
                                ) : (
                                    <MainChart months={months} selectedKey={activeKey} onSelect={setMonthKey} />
                                )}
                            </SectionCard>

                            {/* 5. Daily revenue and payment methods */}
                            <div className="grid gap-5 md:gap-6 xl:grid-cols-2">
                                <SectionCard
                                    title="درآمد روزانه"
                                    subtitle={selected ? `${selected.label_fa}` : undefined}
                                >
                                    {selected?.daily ? (
                                        <DailyChart days={selected.daily} monthKey={selected.key} />
                                    ) : (
                                        <Quiet />
                                    )}
                                </SectionCard>
                                {selected ? (
                                    <MethodsCard s={selected} />
                                ) : (
                                    <SectionCard title="روش‌های پرداخت">
                                        <Quiet />
                                    </SectionCard>
                                )}
                            </div>

                            {/* 6. Price bands and customers */}
                            <div className="grid gap-5 md:gap-6 xl:grid-cols-2">
                                {selected ? (
                                    <>
                                        <PriceBandsCard s={selected} />
                                        <CustomersCard s={selected} />
                                    </>
                                ) : (
                                    <>
                                        <SectionCard title="قیمت فروش هر گیگ">
                                            <Quiet />
                                        </SectionCard>
                                        <SectionCard title="مشتریان">
                                            <Quiet />
                                        </SectionCard>
                                    </>
                                )}
                            </div>

                            {/* 7. Receivables and unit economics */}
                            <div className="grid gap-5 md:gap-6 xl:grid-cols-2">
                                <ReceivablesCard r={data.receivables} />
                                {selected && settings ? (
                                    <UnitEconomicsCard s={selected} settings={settings} />
                                ) : (
                                    <SectionCard title="بهره‌وری هر گیگ">
                                        <Quiet />
                                    </SectionCard>
                                )}
                            </div>

                            {/* 8. Per panel */}
                            <SectionCard
                                title="به تفکیک پنل"
                                subtitle={selected ? `${selected.label_fa} · فروش هر پنل و سود آن` : undefined}
                            >
                                {selected ? <PanelTable key={selected.key} rows={selected.per_admin} /> : <Quiet />}
                            </SectionCard>

                            {/* 9. Black Friday */}
                            {data.black_friday &&
                                (data.black_friday.active ||
                                    data.black_friday.purchases > 0 ||
                                    data.black_friday.settlements > 0) && <BlackFridayCard bf={data.black_friday} />}
                        </>
                    )}
                </div>
            </div>

            {settings && (
                <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} settings={settings} onSaved={refresh} />
            )}
        </PageLayout>
    )
}

/** The table twin of the main chart: every value the chart shows, readable without hover. */
function MonthsTable({ months }: { months: NonNullable<ProfitOverview['months']> }) {
    return (
        <Table>
            <TableHeader>
                <TableRow className="hover:bg-transparent">
                    {['ماه', 'درآمد', 'هزینه', 'سود خالص', 'حاشیه سود'].map((h, i) => (
                        <TableHead key={h} className={cn('pf-body whitespace-nowrap px-3 font-bold', i === 0 ? 'text-start' : 'text-end')}>
                            {h}
                        </TableHead>
                    ))}
                </TableRow>
            </TableHeader>
            <TableBody>
                {months.map((m) => (
                    <TableRow key={m.key}>
                        <TableCell className="pf-body whitespace-nowrap px-3 text-start font-bold">{m.label_fa}</TableCell>
                        <TableCell className="pf-body whitespace-nowrap px-3 text-end">
                            <Num>{fa(m.revenue)}</Num>
                        </TableCell>
                        <TableCell className="pf-body whitespace-nowrap px-3 text-end">
                            <Num>{fa(m.cost + m.fixed_cost)}</Num>
                        </TableCell>
                        <TableCell
                            className={cn('pf-body whitespace-nowrap px-3 text-end font-bold', m.net_profit < 0 && 'text-destructive')}
                        >
                            <Num>{fa(m.net_profit)}</Num>
                        </TableCell>
                        <TableCell className="pf-body whitespace-nowrap px-3 text-end">
                            <Num>{faPercent(m.margin, 1)}</Num>
                        </TableCell>
                    </TableRow>
                ))}
            </TableBody>
        </Table>
    )
}

/** Placeholders the size of each card, so nothing jumps when data arrives. */
function Skeletons() {
    return (
        <div className="space-y-5 md:space-y-6" aria-busy="true" aria-label="در حال بارگذاری">
            <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3 xl:grid-cols-6">
                {Array.from({ length: 6 }, (_, i) => (
                    <SkeletonCard key={i} height="116px" compact />
                ))}
            </div>
            <SkeletonCard height="180px" />
            <SkeletonCard height="420px" />
            <div className="grid gap-5 md:gap-6 xl:grid-cols-2">
                <SkeletonCard height="380px" />
                <SkeletonCard height="380px" />
            </div>
            <div className="grid gap-5 md:gap-6 xl:grid-cols-2">
                <SkeletonCard height="400px" />
                <SkeletonCard height="400px" />
            </div>
            <div className="grid gap-5 md:gap-6 xl:grid-cols-2">
                <SkeletonCard height="460px" />
                <SkeletonCard height="460px" />
            </div>
            <SkeletonCard height="720px" />
        </div>
    )
}
