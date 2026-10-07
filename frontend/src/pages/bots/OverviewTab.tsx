import { BotAPI, BotInfo, BotStats } from '@/lib/bots-api'
import { ErrorBox, Loading, Stat, money, num, useLoad } from './common'

export function OverviewTab({ api, info }: { api: BotAPI; info: BotInfo | null }) {
    const { data: s, loading, error } = useLoad(() => api.get<BotStats>('stats'), [api])
    if (loading && !s) return <Loading />
    return (
        <div className="space-y-4">
            <ErrorBox error={error} />
            {s && (
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                    <Stat label="کاربران" value={num(s.users)} sub={`${num(s.blocked_users)} مسدود`} />
                    <Stat label="سرویس‌های فعال" value={num(s.active_services)} sub={`${num(s.test_accounts)} اکانت تست`} />
                    <Stat label="فروش ۲۴ ساعت" value={num(s.sales_24h)} sub={money(s.sales_24h_amount)} />
                    <Stat label="جمع فروش سرویس‌های فعال" value={money(s.sales_total)} />
                    <Stat label="پرداخت‌های در انتظار" value={num(s.pending_payments)} />
                    <Stat label="جمع پرداخت‌های تأییدشده" value={money(s.paid_total)} />
                    <Stat label="موجودی کیف پول کاربران" value={money(s.wallet_total)} />
                    <Stat label="درخواست‌های بازگشت وجه" value={num(s.cancel_requests)} />
                </div>
            )}
            {info && (
                <p className="text-xs text-muted-foreground" dir="ltr">
                    @{info.bot_username} · {info.domain} · v{info.version}
                </p>
            )}
        </div>
    )
}
