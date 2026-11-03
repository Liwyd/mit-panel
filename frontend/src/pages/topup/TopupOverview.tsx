import { BotAPI, TopupStats } from '@/lib/bots-api'
import { Button } from '@/components/ui/button'
import { ErrorBox, Loading, Notice, Stat, money, num, useAction, useLoad } from '../bots/common'

export function TopupOverview({ api }: { api: BotAPI }) {
    const { data: s, loading, error } = useLoad(() => api.get<TopupStats>('stats'), [api])
    const info = useLoad(() => api.get<{ configured: boolean; running: boolean; enabled: boolean }>('info'), [api])
    const act = useAction()
    const lifecycle = async (operation: 'enable' | 'disable') => {
        const text = operation === 'disable' ? 'ربات متوقف شود؟ تا فعال‌سازی دوباره، هیچ پیام یا پردازشی انجام نمی‌دهد.' : 'ربات فعال شود؟'
        if (!window.confirm(text)) return
        const result = await act.run(() => api.post(`lifecycle/${operation}`), operation === 'enable' ? 'ربات فعال شد' : 'ربات متوقف شد')
        if (result) { await info.reload() }
    }
    if (loading && !s) return <Loading />
    return (
        <div className="space-y-4">
            <ErrorBox error={error} />
            {s && (
                <div className="space-y-4">
                    <div className="rounded-xl border border-border bg-card p-3 text-sm">
                        <span className={s.running ? 'text-brand-green' : s.configured ? 'text-amber-600' : 'text-destructive'}>
                            {s.running ? '● ربات در حال اجرا است' : s.configured ? '● توکن تنظیم شده، اما ربات در این پردازش اجرا نیست' : '● توکن ربات هنوز تنظیم نشده است'}
                        </span>
                        {info.data && <Button className="mr-3" size="sm" variant={info.data.running ? 'destructive' : 'default'} disabled={act.busy || (!info.data.running && !info.data.configured)} onClick={() => lifecycle(info.data.running ? 'disable' : 'enable')}>
                            {info.data.running ? 'توقف ربات' : 'فعال‌سازی ربات'}
                        </Button>}
                    </div>
                    <ErrorBox error={act.error || info.error} /><Notice text={act.notice} />
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                        <Stat label="فروش امروز" value={money(s.sales_today_amount)} sub={`${num(s.sales_today)} خرید · ${num(s.sales_today_gb)} گیگ`} />
                        <Stat label="رسیدهای در انتظار" value={num(s.pending_requests)} sub={money(s.pending_amount)} />
                        <Stat label="بدهی‌های باز" value={money(s.open_bills_amount)} sub={`${num(s.open_bills)} مورد`} />
                        <Stat label="سررسید گذشته" value={money(s.overdue_amount)} sub={`${num(s.overdue_bills)} مورد`} />
                        <Stat label="کاربران ربات" value={num(s.users)} sub={`${num(s.linked_users)} نماینده با پنل`} />
                        <Stat label="پنل‌های مسدود" value={num(s.locked_panels)} />
                    </div>
                </div>
            )}
        </div>
    )
}
