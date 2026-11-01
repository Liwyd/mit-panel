import { BotAPI, TopupStats } from '@/lib/bots-api'
import { ErrorBox, Loading, Stat, money, num, useLoad } from '../bots/common'

export function TopupOverview({ api }: { api: BotAPI }) {
    const { data: s, loading, error } = useLoad(() => api.get<TopupStats>('stats'), [api])
    if (loading && !s) return <Loading />
    return (
        <div className="space-y-4">
            <ErrorBox error={error} />
            {s && (
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                    <Stat label="فروش امروز" value={money(s.sales_today_amount)} sub={`${num(s.sales_today)} خرید · ${num(s.sales_today_gb)} گیگ`} />
                    <Stat label="رسیدهای در انتظار" value={num(s.pending_requests)} sub={money(s.pending_amount)} />
                    <Stat label="بدهی‌های باز" value={money(s.open_bills_amount)} sub={`${num(s.open_bills)} مورد`} />
                    <Stat label="سررسید گذشته" value={money(s.overdue_amount)} sub={`${num(s.overdue_bills)} مورد`} />
                    <Stat label="کاربران ربات" value={num(s.users)} sub={`${num(s.linked_users)} نماینده با پنل`} />
                    <Stat label="پنل‌های مسدود" value={num(s.locked_panels)} />
                </div>
            )}
        </div>
    )
}
