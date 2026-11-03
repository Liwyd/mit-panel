import { useState } from 'react'
import { Check, ExternalLink, RefreshCw, X } from 'lucide-react'
import { BotAPI, TopupRequest } from '@/lib/bots-api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBox, Loading, Notice, Spinner, money, num, useAction, useLoad, when } from '../bots/common'

const KIND: Record<string, string> = {
    topup: 'شارژ حجم',
    wallet: 'شارژ کیف پول',
    invoice: 'پرداخت فاکتور',
    settlement: 'تسویه بدهی',
}

export function TopupRequests({ api }: { api: BotAPI }) {
    const remote = useLoad(() => api.get<TopupRequest[]>('requests'), [api])
    const act = useAction()
    const [receipt, setReceipt] = useState<{ id: number; url: string } | null>(null)

    if (remote.loading && !remote.data) return <Loading />
    if (!remote.data) return <ErrorBox error={remote.error} />

    const showReceipt = async (request: TopupRequest) => {
        if (!request.has_receipt) return
        if (receipt?.id === request.id) {
            URL.revokeObjectURL(receipt.url)
            setReceipt(null)
            return
        }
        const url = await act.run(() => api.blobURL(`requests/${request.id}/receipt`))
        if (typeof url === 'string') {
            if (receipt) URL.revokeObjectURL(receipt.url)
            setReceipt({ id: request.id, url })
        }
    }

    const approve = async (request: TopupRequest) => {
        if (!window.confirm(`رسید #${request.id} تأیید شود؟ این عملیات ممکن است حجم یا موجودی کاربر را تغییر دهد.`)) return
        const result = await act.run(() => api.post(`requests/${request.id}/approve`), 'رسید تأیید شد')
        if (result) await remote.reload()
    }

    const reject = async (request: TopupRequest) => {
        const raw = window.prompt('دلیل رد رسید را وارد کنید. برای رد بدون دلیل، خالی بگذارید.')
        if (raw === null) return
        const result = await act.run(() => api.post(`requests/${request.id}/reject`, { reason: raw }), 'رسید رد شد')
        if (result) await remote.reload()
    }

    return (
        <Card>
            <CardHeader>
                <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                        <CardTitle>رسیدهای در انتظار</CardTitle>
                        <CardDescription className="leading-6 mt-1">
                            تأیید و رد از همین صف، همان کنترل اتمیک ربات تلگرام را استفاده می‌کند؛ رسید دوبار اعمال نمی‌شود.
                        </CardDescription>
                    </div>
                    <Button variant="outline" size="sm" disabled={remote.loading} onClick={() => remote.reload()}>
                        <RefreshCw className="ml-1 h-4 w-4" /> بروزرسانی
                    </Button>
                </div>
            </CardHeader>
            <CardContent className="space-y-4">
                <ErrorBox error={remote.error || act.error} />
                <Notice text={act.notice} />
                {remote.data.length === 0 ? (
                    <p className="py-8 text-center text-sm text-muted-foreground">رسید در انتظاری وجود ندارد.</p>
                ) : (
                    <div className="space-y-3">
                        {remote.data.map((request) => (
                            <article key={request.id} className="rounded-xl border border-border p-4">
                                <div className="flex flex-wrap items-start justify-between gap-3">
                                    <div className="space-y-1 text-sm">
                                        <div className="font-semibold">#{num(request.id)} · {KIND[request.kind] || request.kind}</div>
                                        <div className="text-muted-foreground">
                                            کاربر: <bdi dir="ltr">{num(request.telegram_id)}</bdi>{request.username ? <> · پنل: <bdi dir="ltr">{request.username}</bdi></> : null}
                                        </div>
                                        {request.requested_gb > 0 && <div>حجم: {num(request.requested_gb)} گیگابایت</div>}
                                        <div>مبلغ: {money(request.amount)}</div>
                                        <div className="text-xs text-muted-foreground">ثبت: {when(request.created_at)}</div>
                                    </div>
                                    <div className="flex flex-wrap gap-2">
                                        {request.has_receipt && (
                                            <Button variant="outline" size="sm" disabled={act.busy} onClick={() => showReceipt(request)}>
                                                <ExternalLink className="ml-1 h-4 w-4" /> {receipt?.id === request.id ? 'بستن رسید' : 'مشاهده رسید'}
                                            </Button>
                                        )}
                                        <Button size="sm" disabled={act.busy} onClick={() => approve(request)}>
                                            {act.busy ? <Spinner className="ml-1" /> : <Check className="ml-1 h-4 w-4" />} تأیید
                                        </Button>
                                        <Button size="sm" variant="destructive" disabled={act.busy} onClick={() => reject(request)}>
                                            <X className="ml-1 h-4 w-4" /> رد
                                        </Button>
                                    </div>
                                </div>
                                {receipt?.id === request.id && <img src={receipt.url} alt={`رسید ${request.id}`} className="mt-4 max-h-[38rem] w-auto max-w-full rounded-lg border border-border" />}
                            </article>
                        ))}
                    </div>
                )}
            </CardContent>
        </Card>
    )
}
