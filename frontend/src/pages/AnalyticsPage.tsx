import { useCallback, useEffect, useState } from 'react'
import { Activity, CalendarClock, RefreshCw, ShoppingCart, TrendingUp } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { BarChart } from '@/components/charts/BarChart'
import { analyticsAPI } from '@/lib/api'
import { getUserRole } from '@/lib/auth'
import { cn } from '@/lib/utils'
import { AdminAnalytics, AnalyticsNodePeriod } from '@/types'

const NODE_PERIODS: { value: AnalyticsNodePeriod; label: string }[] = [
    { value: '1d', label: '۲۴ ساعت' },
    { value: '7d', label: '۷ روز' },
    { value: '30d', label: '۳۰ روز' },
]

// Silent refresh; the usage behind it only moves with each Marzban sync.
const POLL_MS = 60_000

const FA_DIGITS = '۰۱۲۳۴۵۶۷۸۹'

/** Latin digits to Persian, for numbers inside Persian text. */
function fa(value: string | number): string {
    return String(value).replace(/\d/g, (d) => FA_DIGITS[Number(d)])
}

const FA_UNITS = ['بایت', 'کیلوبایت', 'مگ', 'گیگ', 'ترابایت']

/** "38.5 GB" -> "۳۸٫۵ گیگ". Negative values keep their sign. */
function traffic(bytes: number): string {
    if (!bytes) return '۰'
    if (bytes < 0) return `-${traffic(-bytes)}`
    const i = Math.min(FA_UNITS.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)))
    const value = parseFloat((bytes / Math.pow(1024, i)).toFixed(2))
    return `${fa(String(value).replace('.', '٫'))} ${FA_UNITS[i]}`
}

/** Backend timestamps are naive UTC. */
function parseUtc(iso: string): Date {
    return new Date(iso.endsWith('Z') ? iso : `${iso}Z`)
}

/** "2026-11-16" (already a local date) -> "۲۵ آبان", or with the weekday. */
function dayLabel(date: string, long = false): string {
    const d = new Date(`${date}T00:00:00`)
    return d.toLocaleDateString(
        'fa-IR',
        long ? { weekday: 'long', day: 'numeric', month: 'long' } : { day: 'numeric', month: 'short' }
    )
}

function changeText(today: number, yesterday: number): string {
    if (yesterday <= 0) return today > 0 ? 'دیروز مصرفی نداشتید' : 'هنوز مصرفی ثبت نشده'
    const pct = Math.round(((today - yesterday) / yesterday) * 100)
    if (pct === 0) return `هم‌اندازه‌ی دیروز (${traffic(yesterday)})`
    return `${fa(Math.abs(pct))}٪ ${pct > 0 ? 'بیشتر' : 'کمتر'} از کل دیروز (${traffic(yesterday)})`
}

function StatCard({
    title,
    icon: Icon,
    value,
    caption,
    hint,
    valueClass,
}: {
    title: string
    icon: typeof Activity
    value: string
    caption: string
    /** What the number means, in plain words. */
    hint: string
    valueClass?: string
}): JSX.Element {
    return (
        <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">{title}</CardTitle>
                <Icon className="h-4 w-4 text-primary" />
            </CardHeader>
            <CardContent className="space-y-1">
                <div className={cn('text-2xl font-bold', valueClass)}>{value}</div>
                <p className="text-xs text-muted-foreground">{caption}</p>
                <p className="border-t pt-2 text-xs leading-5 text-muted-foreground/80">{hint}</p>
            </CardContent>
        </Card>
    )
}

function RunwayCard({ data }: { data: AdminAnalytics }): JSX.Element {
    const { days_left, runs_out_at, window_days } = data.sales
    let value: string
    let caption: string
    let tone: string | undefined
    if (data.remaining <= 0) {
        value = 'تمام شده'
        caption = 'حجم شما به پایان رسیده'
        tone = 'text-destructive'
    } else if (days_left === null) {
        value = '—'
        caption = `در ${fa(window_days)} روز گذشته فروشی نداشتید، پس حجمتان فعلاً کم نمی‌شود`
    } else {
        value = days_left < 1 ? 'کمتر از ۱ روز' : `${fa(Math.floor(days_left))} روز دیگر`
        caption = runs_out_at
            ? `حدود ${parseUtc(runs_out_at).toLocaleDateString('fa-IR', { weekday: 'long', day: 'numeric', month: 'long' })}`
            : 'با همین روند فروش'
        tone = days_left < 3 ? 'text-destructive' : days_left < 7 ? 'text-amber-500' : undefined
    }
    return (
        <StatCard
            title="حجم شما تمام می‌شود در"
            icon={CalendarClock}
            value={value}
            caption={caption}
            hint={`حجم باقی‌مانده‌ی شما (${traffic(data.remaining)}) تقسیم بر میانگین فروش روزانه؛ یعنی اگر مثل ${fa(window_days)} روز گذشته بفروشید، کی باید حجم بخرید.`}
            valueClass={tone}
        />
    )
}

function NodeRanking({ nodes }: { nodes: AdminAnalytics['nodes'] }): JSX.Element {
    if (nodes.items === null) {
        return <p className="py-6 text-center text-sm text-muted-foreground">ارتباط با سرور برقرار نشد؛ کمی بعد دوباره امتحان کنید.</p>
    }
    if (nodes.items.length === 0) {
        return <p className="py-6 text-center text-sm text-muted-foreground">کاربران شما در این بازه از هیچ سروری استفاده نکرده‌اند.</p>
    }
    const top = nodes.items[0].used
    return (
        <ol className="space-y-3">
            {nodes.items.map((node, i) => {
                const share = nodes.total > 0 ? (node.used / nodes.total) * 100 : 0
                return (
                    <li key={`${node.id ?? 'master'}-${node.name}`} className="space-y-1.5">
                        <div className="flex items-baseline justify-between gap-3 text-sm">
                            <span className="min-w-0 truncate font-medium">
                                <span className="ml-2 text-muted-foreground">{fa(i + 1)}.</span>
                                {node.name}
                            </span>
                            <span className="shrink-0 text-muted-foreground">
                                <span className="font-semibold text-foreground">{traffic(node.used)}</span>
                                {' · '}
                                {share < 1 ? 'کمتر از ۱' : fa(Math.round(share))}٪
                            </span>
                        </div>
                        <div className="h-2 w-full rounded-full bg-muted">
                            <div
                                className="h-2 rounded-full"
                                style={{ width: `${Math.max(1, (node.used / top) * 100)}%`, background: 'hsl(var(--brand-blue))' }}
                            />
                        </div>
                    </li>
                )
            })}
        </ol>
    )
}

export function AnalyticsPage(): JSX.Element {
    const role = getUserRole()
    const [data, setData] = useState<AdminAnalytics | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [loading, setLoading] = useState(true)
    const [refreshing, setRefreshing] = useState(false)
    const [nodePeriod, setNodePeriod] = useState<AnalyticsNodePeriod>('1d')

    const load = useCallback(
        async (silent: boolean) => {
            if (!silent) setRefreshing(true)
            try {
                setData(await analyticsAPI.get(nodePeriod))
                setError(null)
            } catch {
                if (!silent) setError('دریافت اطلاعات ناموفق بود؛ دوباره امتحان کنید.')
            } finally {
                setLoading(false)
                setRefreshing(false)
            }
        },
        [nodePeriod]
    )

    useEffect(() => {
        if (role !== 'admin') return
        load(false)
        const timer = setInterval(() => load(true), POLL_MS)
        return () => clearInterval(timer)
    }, [role, load])

    if (role !== 'admin') {
        return (
            <div dir="rtl" className="p-4 md:p-6">
                <p className="text-muted-foreground">این صفحه مخصوص ادمین‌هاست.</p>
            </div>
        )
    }

    const usage = data?.usage
    const sales = data?.sales
    const recordingSince = usage?.since ? parseUtc(usage.since) : null
    const shortHistory = !recordingSince || Date.now() - recordingSince.getTime() < 24 * 3600 * 1000

    return (
        <div dir="rtl" className="space-y-6 p-4 md:p-6 max-w-full overflow-x-hidden">
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                    <h1 className="text-2xl md:text-3xl font-bold tracking-tight">Analytics</h1>
                    <p className="text-muted-foreground">
                        مصرف کاربران شما، میزان فروشتان و پیش‌بینی اینکه حجمتان کی تمام می‌شود
                    </p>
                </div>
                <Button variant="outline" size="sm" onClick={() => load(false)} disabled={refreshing}>
                    <RefreshCw className={cn('h-4 w-4 ml-2', refreshing && 'animate-spin')} />
                    {refreshing ? 'Refreshing...' : 'Refresh'}
                </Button>
            </div>

            {error && (
                <div className="rounded-md bg-destructive/10 p-4 text-sm text-destructive border border-destructive/20">{error}</div>
            )}

            {loading && !data && <p className="text-sm text-muted-foreground">در حال بارگذاری...</p>}

            {data && usage && sales && (
                <>
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                        <StatCard
                            title="مصرف امروز"
                            icon={Activity}
                            value={traffic(usage.today)}
                            caption={changeText(usage.today, usage.yesterday)}
                            hint="مجموع حجمی که همه‌ی کاربران شما از ساعت ۰۰:۰۰ امروز مصرف کرده‌اند."
                        />
                        <StatCard
                            title="میانگین فروش روزانه"
                            icon={ShoppingCart}
                            value={traffic(sales.per_day)}
                            caption={`میانگین فروش ${fa(sales.window_days)} روز گذشته`}
                            hint={`کل فروش ${fa(sales.window_days)} روز گذشته تقسیم بر ${fa(sales.window_days)}: ساخت کاربر جدید، تمدید و افزایش حجم، منهای حجم‌هایی که برگشت خورده.`}
                        />
                        <StatCard
                            title="پیش‌بینی فروش فردا"
                            icon={TrendingUp}
                            value={traffic(sales.tomorrow)}
                            caption={`بر اساس فروش ${fa(sales.tomorrow_window_hours)} ساعت گذشته`}
                            hint={`اگر فردا هم به اندازه‌ی ${fa(sales.tomorrow_window_hours)} ساعت گذشته بفروشید، حدوداً این مقدار حجم برای کاربران جدید از حساب شما کم می‌شود.`}
                        />
                        <RunwayCard data={data} />
                    </div>

                    {sales.days_covered < sales.window_days && (
                        <p className="text-xs text-muted-foreground">
                            سابقه‌ی فروش فعلاً {fa(sales.days_covered)} روز از {fa(sales.window_days)} روز را پوشش
                            می‌دهد؛ با جمع شدن اطلاعات، پیش‌بینی‌ها دقیق‌تر می‌شوند.
                        </p>
                    )}

                    <Card>
                        <CardHeader className="pb-2">
                            <CardTitle className="text-base">مصرف ساعت به ساعت — ۲۴ ساعت گذشته</CardTitle>
                            <p className="text-xs leading-5 text-muted-foreground">
                                {shortHistory
                                    ? recordingSince
                                        ? `ثبت مصرف از ${recordingSince.toLocaleString('fa-IR', { hour: '2-digit', minute: '2-digit', month: 'long', day: 'numeric' })} شروع شده است.`
                                        : 'ثبت مصرف با همگام‌سازی بعدی کاربران شروع می‌شود (حداکثر ۱۰ دقیقه).'
                                    : 'مصرف همه‌ی کاربران شما در هر ساعت؛ نشان می‌دهد کاربرانتان بیشتر چه ساعت‌هایی از سرویس استفاده می‌کنند.'}{' '}
                                ستون کم‌رنگ، ساعت جاری است که هنوز تمام نشده.
                            </p>
                        </CardHeader>
                        <CardContent>
                            <BarChart
                                data={usage.hourly.map((h, i) => ({
                                    label: fa(h.label),
                                    title: `ساعت ${fa(h.label)} تا ${fa(String((Number(h.label.slice(0, 2)) + 1) % 24).padStart(2, '0'))}:۰۰`,
                                    value: h.used,
                                    muted: i === usage.hourly.length - 1,
                                }))}
                                format={traffic}
                                labelEvery={3}
                            />
                        </CardContent>
                    </Card>

                    <div className="grid gap-4 lg:grid-cols-2">
                        <Card>
                            <CardHeader className="pb-2">
                                <CardTitle className="text-base">مصرف روزانه — ۷ روز گذشته</CardTitle>
                                <p className="text-xs leading-5 text-muted-foreground">
                                    مجموع مصرف کاربران شما در هر روز. ستون کم‌رنگ امروز است که هنوز تمام نشده.
                                </p>
                            </CardHeader>
                            <CardContent>
                                <BarChart
                                    data={usage.daily.map((d, i) => ({
                                        label: dayLabel(d.date),
                                        title: dayLabel(d.date, true),
                                        value: d.used,
                                        muted: i === usage.daily.length - 1,
                                    }))}
                                    format={traffic}
                                    height={220}
                                />
                            </CardContent>
                        </Card>

                        <Card>
                            <CardHeader className="pb-2">
                                <CardTitle className="text-base">فروش روزانه — ۷ روز گذشته</CardTitle>
                                <p className="text-xs leading-5 text-muted-foreground">
                                    حجمی که هر روز برای ساخت، تمدید یا افزایش حجم کاربران از حساب شما کم شده، منهای
                                    حجم برگشتی. پیش‌بینی‌های بالا از روی همین نمودار حساب می‌شوند.
                                </p>
                            </CardHeader>
                            <CardContent>
                                <BarChart
                                    data={sales.daily.map((d, i) => ({
                                        label: dayLabel(d.date),
                                        title: dayLabel(d.date, true),
                                        value: d.sold,
                                        muted: i === sales.daily.length - 1,
                                    }))}
                                    format={traffic}
                                    height={220}
                                    color="hsl(var(--brand-green))"
                                />
                            </CardContent>
                        </Card>
                    </div>

                    <Card>
                        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0 pb-4">
                            <div>
                                <CardTitle className="text-base">پرمصرف‌ترین سرورها</CardTitle>
                                <p className="text-xs leading-5 text-muted-foreground">
                                    کاربران شما بیشتر از کدام سرور (لوکیشن) استفاده می‌کنند، به ترتیب مصرف.
                                </p>
                            </div>
                            <div className="flex rounded-md border p-0.5">
                                {NODE_PERIODS.map((p) => (
                                    <button
                                        key={p.value}
                                        type="button"
                                        onClick={() => setNodePeriod(p.value)}
                                        className={cn(
                                            'rounded px-3 py-1 text-xs font-medium transition-colors',
                                            nodePeriod === p.value
                                                ? 'bg-primary text-primary-foreground'
                                                : 'text-muted-foreground hover:text-foreground'
                                        )}
                                    >
                                        {p.label}
                                    </button>
                                ))}
                            </div>
                        </CardHeader>
                        <CardContent>
                            <NodeRanking nodes={data.nodes} />
                        </CardContent>
                    </Card>
                </>
            )}
        </div>
    )
}
