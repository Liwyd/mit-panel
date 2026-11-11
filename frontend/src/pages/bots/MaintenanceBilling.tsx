import { useCallback, useEffect, useState } from 'react'
import { maintenanceAPI, MaintenanceOverview, TelegramBot } from '@/lib/bots-api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBox, Notice, Spinner, Switch, useAction } from './common'

function dateLabel(value: string | null): string {
    return value ? new Date(value).toLocaleString('fa-IR', { timeZone: 'Asia/Tehran' }) : '—'
}

const statusLabels: Record<string, string> = { pending: 'در انتظار پرداخت', paid: 'پرداخت‌شده', cancelled: 'لغوشده' }

export function MaintenanceBilling({ revision }: { revision: TelegramBot[] }) {
    const [data, setData] = useState<MaintenanceOverview | null>(null)
    const [price, setPrice] = useState('')
    const act = useAction()
    const [loadError, setLoadError] = useState<string | null>(null)
    const load = useCallback(async () => {
        const next = await maintenanceAPI.get()
        setData(next)
        setLoadError(null)
        return next
    }, [])

    useEffect(() => {
        let live = true
        maintenanceAPI.get().then((next) => {
            if (live) { setData(next); setPrice(next.eur_price); setLoadError(null) }
        }).catch((err: unknown) => {
            if (live) setLoadError(err instanceof Error ? err.message : 'دریافت وضعیت ناموفق بود')
        })
        return () => { live = false }
    }, [revision])

    return (
        <Card>
            <CardHeader>
                <CardTitle>فاکتور ماهانه نگهداری ربات</CardTitle>
                <CardDescription>
                    برای هر ربات جداگانه فعال کنید. اولین فاکتور در اجرای بعدی (حداکثر یک دقیقه) و سپس هر ماه صادر می‌شود.
                    نرخ بازار آزاد یورو از PriceDB / TGJU دریافت و مبلغ به تومان ثبت می‌شود؛ کلید API لازم نیست.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                <ErrorBox error={loadError || act.error} />
                <Notice text={act.notice} />
                <div className="flex flex-wrap items-end gap-2">
                    <div className="space-y-1">
                        <label htmlFor="maintenance-price" className="text-sm font-medium">هزینه هر ربات در ماه (یورو)</label>
                        <Input id="maintenance-price" dir="ltr" inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} placeholder="1.00" />
                    </div>
                    <Button disabled={act.busy || !data || !price} onClick={() => act.run(async () => {
                        const saved = await maintenanceAPI.setPrice(price)
                        setPrice(saved.eur_price)
                        await load()
                    }, 'قیمت ذخیره شد؛ فقط فاکتورهای آینده تغییر می‌کنند.')}>
                        ذخیره قیمت
                    </Button>
                    <Button variant="outline" disabled={act.busy} onClick={() => act.run(load)}>تازه‌سازی</Button>
                    {act.busy && <Spinner />}
                </div>
                {data && !data.running && <p className="text-sm text-amber-600">ربات صدور فاکتور در حال اجرا نیست. برای فعال‌سازی صدور، ابتدا ربات اصلی را پیکربندی و اجرا کنید.</p>}
                <p className="text-sm text-muted-foreground">
                    مهلت پرداخت سه روز پس از ارسال موفق فاکتور است؛ سپس با ۱۲ ساعت مهلت اضافی، قفل موجود داشبورد اعمال می‌شود.
                    غیرفعال‌سازی فاکتورهای قبلی را حذف نمی‌کند. ربات یا ادمین غیرفعال و ادمین ناظر، فاکتور جدید دریافت نمی‌کنند.
                </p>
                {data?.bots.map((item) => (
                    <div key={item.bot_id} className="rounded-lg border border-border p-3 space-y-2">
                        <div className="font-semibold">{item.bot_name} <span className="font-normal text-sm text-muted-foreground">— {item.admin_username || 'بدون ادمین'}</span></div>
                        <Switch checked={item.enabled} disabled={act.busy || (!item.enabled && (!data.running || !item.eligible))} onChange={(enabled) => {
                            if (act.busy || (enabled && (!data.running || !item.eligible))) return
                            void act.run(async () => { await maintenanceAPI.setEnabled(item.bot_id, enabled); await load() }, 'تنظیم صدور فاکتور ذخیره شد.')
                        }} label="ارسال خودکار فاکتور نگهداری" hint={!item.eligible ? 'برای فعال‌سازی، ربات و ادمین فعال با شناسه تلگرام معتبر لازم است؛ ادمین نباید ناظر باشد.' : undefined} />
                        <div className="text-xs text-muted-foreground">تاریخ اجرای بعدی: {dateLabel(item.next_due_at)}{!item.enabled && ' (صدور غیرفعال)'}</div>
                        {item.latest_invoice && <div className="text-sm">
                            آخرین فاکتور #{item.latest_invoice.invoice_id}: {item.latest_invoice.amount.toLocaleString('fa-IR')} تومان — {statusLabels[item.latest_invoice.status] || item.latest_invoice.status}
                            {item.latest_invoice.status === 'pending' && <span className="block text-xs text-muted-foreground">
                                {item.latest_invoice.notified_at ? `سررسید: ${dateLabel(item.latest_invoice.due_at)}` : 'در صف ارسال؛ هنوز سررسید ندارد.'}
                                {item.latest_invoice.last_error && ' ارسال ناموفق بوده؛ تلاش خودکار ادامه دارد.'}
                            </span>}
                        </div>}
                    </div>
                ))}
                {data && !data.bots.length && <p className="text-sm text-muted-foreground">هنوز رباتی ثبت نشده است.</p>}
            </CardContent>
        </Card>
    )
}

