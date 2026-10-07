import { useState } from 'react'
import { Search, Trash2, Copy } from 'lucide-react'
import { BotAPI, BotPanel, BotService, Paged } from '@/lib/bots-api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Empty, ErrorBox, Loading, Notice, Switch, money, num, selectClass, useAction, useLoad, when } from './common'

const PAGE = 30
const STATUS: Record<string, string> = {
    active: 'فعال',
    end_of_time: 'پایان زمان',
    end_of_volume: 'پایان حجم',
    sendedwarn: 'هشدار داده شده',
    unpaid: 'پرداخت نشده',
    removedbyadmin: 'حذف توسط ادمین',
    removebyuser: 'حذف توسط کاربر',
}

// The bot's view of the sold user on the panel behind it.
interface BotLive {
    status?: string
    used_traffic?: string | number
    data_limit?: string | number
    expire?: string | number | null
    subscription_url?: string
}

function gb(bytes: unknown): string {
    const n = Number(bytes || 0)
    if (!n) return '—'
    return (n / 1024 ** 3).toFixed(2).replace(/\.00$/, '') + ' GB'
}

export function ServicesTab({ api }: { api: BotAPI }) {
    const panels = useLoad(() => api.get<BotPanel[]>('panels'), [api])
    const [q, setQ] = useState('')
    const [query, setQuery] = useState('')
    const [status, setStatus] = useState('')
    const [panel, setPanel] = useState('')
    const [offset, setOffset] = useState(0)
    const [selected, setSelected] = useState<string | null>(null)
    const list = useLoad(
        () =>
            api.get<Paged<BotService>>('services', {
                q: query || undefined,
                status: status || undefined,
                panel: panel || undefined,
                limit: PAGE,
                offset,
            }),
        [api, query, status, panel, offset]
    )

    return (
        <div className="space-y-4">
            <Card>
                <CardHeader>
                    <CardTitle>سرویس‌ها</CardTitle>
                    <CardDescription>همه‌ی سرویس‌های فروخته‌شده. جستجو با نام کاربری سرویس، آیدی خریدار یا کد سفارش.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                    <form
                        className="flex flex-wrap gap-2"
                        onSubmit={(e) => {
                            e.preventDefault()
                            setOffset(0)
                            setQuery(q.trim())
                        }}
                    >
                        <Input className="flex-1 min-w-[12rem]" value={q} onChange={(e) => setQ(e.target.value)} placeholder="نام کاربری سرویس یا آیدی" />
                        <select className={selectClass + ' w-40'} value={status} onChange={(e) => { setOffset(0); setStatus(e.target.value) }}>
                            <option value="">همه وضعیت‌ها</option>
                            {Object.entries(STATUS).map(([k, v]) => (
                                <option key={k} value={k}>
                                    {v}
                                </option>
                            ))}
                        </select>
                        <select className={selectClass + ' w-40'} value={panel} onChange={(e) => { setOffset(0); setPanel(e.target.value) }}>
                            <option value="">همه سرورها</option>
                            {panels.data?.map((p) => (
                                <option key={p.id} value={p.name_panel}>
                                    {p.name_panel}
                                </option>
                            ))}
                        </select>
                        <Button type="submit">
                            <Search className="h-4 w-4 ml-1" /> جستجو
                        </Button>
                    </form>
                    <ErrorBox error={list.error} />
                    {list.loading && !list.data ? (
                        <Loading />
                    ) : !list.data?.items.length ? (
                        <Empty text="سرویسی پیدا نشد" />
                    ) : (
                        <div className="divide-y divide-border rounded-lg border border-border">
                            {list.data.items.map((s) => (
                                <button
                                    key={s.id_invoice}
                                    className="flex w-full flex-wrap items-center justify-between gap-2 p-3 text-right hover:bg-accent/50"
                                    onClick={() => setSelected(s.username)}
                                >
                                    <span className="space-y-0.5">
                                        <span className="block font-mono text-sm" dir="ltr">
                                            {s.username}
                                        </span>
                                        <span className="block text-xs text-muted-foreground">
                                            {s.name_product} · {s.Service_location} · کاربر <span dir="ltr">{s.id_user}</span>
                                        </span>
                                    </span>
                                    <Badge variant={s.Status === 'active' ? 'success' : 'secondary'}>{STATUS[s.Status] || s.Status}</Badge>
                                </button>
                            ))}
                        </div>
                    )}
                    {list.data && list.data.total > PAGE && (
                        <div className="flex items-center justify-between pt-1 text-sm">
                            <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                                قبلی
                            </Button>
                            <span className="text-muted-foreground">
                                {offset + 1}–{Math.min(offset + PAGE, list.data.total)} از {num(list.data.total)}
                            </span>
                            <Button size="sm" variant="outline" disabled={offset + PAGE >= list.data.total} onClick={() => setOffset(offset + PAGE)}>
                                بعدی
                            </Button>
                        </div>
                    )}
                </CardContent>
            </Card>
            <ServiceDialog
                api={api}
                username={selected}
                onClose={() => setSelected(null)}
                onChanged={() => {
                    setSelected(null)
                    list.reload()
                }}
            />
        </div>
    )
}

function ServiceDialog({
    api,
    username,
    onClose,
    onChanged,
}: {
    api: BotAPI
    username: string | null
    onClose: () => void
    onChanged: () => void
}) {
    const detail = useLoad(
        () => (username ? api.get<{ invoice: BotService; live: BotLive }>(`services/${encodeURIComponent(username)}`) : Promise.resolve(null)),
        [api, username]
    )
    const act = useAction()
    const [keep, setKeep] = useState(true)
    const inv = detail.data?.invoice
    const live = detail.data?.live || {}
    const onPanel = live && live.status && live.status !== 'Unsuccessful'

    return (
        <Dialog open={!!username} onOpenChange={(o) => !o && onClose()}>
            <DialogContent dir="rtl" className="max-w-lg">
                <DialogHeader className="pr-8 text-right">
                    <DialogTitle className="font-mono" dir="ltr">
                        {username}
                    </DialogTitle>
                </DialogHeader>
                {detail.loading && !inv ? (
                    <Loading />
                ) : !inv ? (
                    <ErrorBox error={detail.error} />
                ) : (
                    <div className="space-y-3 text-sm">
                        <div className="grid grid-cols-2 gap-2">
                            <Row k="محصول" v={inv.name_product} />
                            <Row k="سرور" v={inv.Service_location} />
                            <Row k="قیمت" v={money(inv.price_product)} />
                            <Row k="خرید" v={when(inv.time_sell)} />
                            <Row k="وضعیت در ربات" v={STATUS[inv.Status] || inv.Status} />
                            <Row k="وضعیت روی سرور" v={onPanel ? live.status : 'روی سرور پیدا نشد'} />
                            {onPanel && (
                                <>
                                    <Row k="مصرف" v={`${gb(live.used_traffic)} از ${gb(live.data_limit)}`} />
                                    <Row k="انقضا" v={live.expire ? new Date(Number(live.expire) * 1000).toLocaleDateString('fa-IR') : 'نامحدود'} />
                                </>
                            )}
                        </div>
                        {onPanel && live.subscription_url && (
                            <div className="flex items-center gap-2 rounded-lg border border-border p-2">
                                <code className="flex-1 truncate text-xs" dir="ltr">
                                    {live.subscription_url}
                                </code>
                                <Button size="xs" variant="ghost" onClick={() => navigator.clipboard?.writeText(live.subscription_url ?? '')}>
                                    <Copy className="h-4 w-4" />
                                </Button>
                            </div>
                        )}
                        <ErrorBox error={act.error} />
                        <Notice text={act.notice} />
                        <div className="rounded-lg border border-destructive/30 p-3 space-y-2">
                            <Switch checked={keep} onChange={setKeep} label="سابقه در ربات بماند" hint="سرویس از سرور پاک می‌شود و در ربات «حذف توسط ادمین» ثبت می‌شود." />
                            <Button
                                variant="destructive"
                                disabled={act.busy}
                                onClick={async () => {
                                    if (!confirm(`سرویس ${inv.username} از سرور حذف شود؟`)) return
                                    if (await act.run(() => api.del(`services/${encodeURIComponent(inv.username)}`, keep ? { keep_record: 1 } : undefined))) onChanged()
                                }}
                            >
                                <Trash2 className="h-4 w-4 ml-1" /> حذف سرویس
                            </Button>
                        </div>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    )
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
    return (
        <div className="rounded-lg bg-muted/40 p-2">
            <div className="text-xs text-muted-foreground">{k}</div>
            <div className="font-medium">{v}</div>
        </div>
    )
}
