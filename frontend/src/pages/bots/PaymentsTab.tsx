import { useEffect, useState } from 'react'
import { Check, X, Image as ImageIcon, RefreshCw } from 'lucide-react'
import { BotAPI, BotPayment, BotPaySettings, Paged } from '@/lib/bots-api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Empty, ErrorBox, Field, Loading, Notice, Spinner, Switch, errorText, money, selectClass, useAction, useLoad } from './common'

const METHODS: Record<string, string> = {
    'cart to cart': 'کارت به کارت',
    Nowpayments: 'ارز دیجیتال (NOWPayments)',
    'Currency Rial gateway': 'درگاه ریالی',
    aqayepardakht: 'آقای پرداخت',
    iranpay: 'ایران‌پی',
}
const STATUSES: Record<string, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' | 'success' | 'gold' }> = {
    waiting: { label: 'در انتظار بررسی', variant: 'gold' },
    paid: { label: 'تأیید شده', variant: 'success' },
    reject: { label: 'رد شده', variant: 'destructive' },
    Unpaid: { label: 'پرداخت نشده', variant: 'secondary' },
}

export function PaymentsTab({ api }: { api: BotAPI }) {
    const [status, setStatus] = useState('waiting')
    const [offset, setOffset] = useState(0)
    const list = useLoad(() => api.get<Paged<BotPayment>>('payments', { status: status || undefined, limit: 30, offset }), [api, status, offset])
    const act = useAction()
    const [receipt, setReceipt] = useState<{ order: string; url: string | null; error?: string } | null>(null)
    const [rejecting, setRejecting] = useState<BotPayment | null>(null)
    const [reason, setReason] = useState('')

    const openReceipt = async (p: BotPayment) => {
        setReceipt({ order: p.id_order, url: null })
        try {
            const url = await api.blobURL(`payments/${encodeURIComponent(p.id_order)}/receipt`)
            setReceipt({ order: p.id_order, url })
        } catch (err) {
            setReceipt({ order: p.id_order, url: null, error: errorText(err) })
        }
    }

    useEffect(() => {
        return () => {
            if (receipt?.url) URL.revokeObjectURL(receipt.url)
        }
    }, [receipt])

    return (
        <div className="space-y-4">
            <Card>
                <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
                    <div>
                        <CardTitle>پرداخت‌ها</CardTitle>
                        <CardDescription>
                            رسیدهای کارت به کارت را از همین‌جا تأیید یا رد کنید؛ دقیقاً مثل دکمه‌های داخل ربات عمل می‌کند و هر پرداخت فقط یک
                            بار شارژ می‌شود.
                        </CardDescription>
                    </div>
                    <div className="flex gap-2 items-center">
                        <select
                            className={selectClass + ' w-44'}
                            value={status}
                            onChange={(e) => {
                                setOffset(0)
                                setStatus(e.target.value)
                            }}
                        >
                            <option value="waiting">در انتظار بررسی</option>
                            <option value="paid">تأیید شده</option>
                            <option value="reject">رد شده</option>
                            <option value="Unpaid">پرداخت نشده</option>
                            <option value="">همه</option>
                        </select>
                        <Button size="icon" variant="outline" onClick={list.reload} aria-label="بارگذاری دوباره">
                            <RefreshCw className="h-4 w-4" />
                        </Button>
                    </div>
                </CardHeader>
                <CardContent className="space-y-3">
                    <ErrorBox error={list.error || act.error} />
                    <Notice text={act.notice} />
                    {list.loading && !list.data ? (
                        <Loading />
                    ) : !list.data?.items.length ? (
                        <Empty text="پرداختی نیست" />
                    ) : (
                        list.data.items.map((p) => (
                            <div key={p.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border p-3">
                                <div className="space-y-1 min-w-0">
                                    <div className="flex flex-wrap items-center gap-2">
                                        <b>{money(p.price)}</b>
                                        <Badge variant={STATUSES[p.payment_Status]?.variant || 'outline'}>
                                            {STATUSES[p.payment_Status]?.label || p.payment_Status}
                                        </Badge>
                                        {p.for_purchase && <Badge variant="outline">خرید سرویس</Badge>}
                                    </div>
                                    <div className="text-xs text-muted-foreground">
                                        {METHODS[p.Payment_Method] || p.Payment_Method} · کاربر <span dir="ltr">{p.id_user}</span> · {p.time}
                                    </div>
                                    <div className="text-xs text-muted-foreground font-mono" dir="ltr">
                                        {p.id_order}
                                    </div>
                                    {p.dec_not_confirmed && p.payment_Status === 'reject' && (
                                        <div className="text-xs text-destructive">دلیل: {p.dec_not_confirmed}</div>
                                    )}
                                </div>
                                <div className="flex gap-1">
                                    {p.has_receipt && (
                                        <Button size="sm" variant="outline" onClick={() => openReceipt(p)}>
                                            <ImageIcon className="h-4 w-4 ml-1" /> رسید
                                        </Button>
                                    )}
                                    {p.payment_Status === 'waiting' && (
                                        <>
                                            <Button
                                                size="sm"
                                                disabled={act.busy}
                                                onClick={async () => {
                                                    if (!confirm(`پرداخت ${money(p.price)} کاربر ${p.id_user} تأیید شود؟`)) return
                                                    if (await act.run(() => api.post(`payments/${encodeURIComponent(p.id_order)}/approve`), 'پرداخت تأیید شد و به کاربر اطلاع داده شد'))
                                                        list.reload()
                                                }}
                                            >
                                                <Check className="h-4 w-4 ml-1" /> تأیید
                                            </Button>
                                            <Button
                                                size="sm"
                                                variant="outline"
                                                disabled={act.busy}
                                                onClick={() => {
                                                    setReason('')
                                                    setRejecting(p)
                                                }}
                                            >
                                                <X className="h-4 w-4 ml-1 text-destructive" /> رد
                                            </Button>
                                        </>
                                    )}
                                </div>
                            </div>
                        ))
                    )}
                    {list.data && list.data.total > 30 && (
                        <div className="flex items-center justify-between pt-2 text-sm">
                            <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 30))}>
                                قبلی
                            </Button>
                            <span className="text-muted-foreground">
                                {offset + 1}–{Math.min(offset + 30, list.data.total)} از {list.data.total}
                            </span>
                            <Button size="sm" variant="outline" disabled={offset + 30 >= list.data.total} onClick={() => setOffset(offset + 30)}>
                                بعدی
                            </Button>
                        </div>
                    )}
                </CardContent>
            </Card>

            <PaySettingsCard api={api} />

            <Dialog open={!!receipt} onOpenChange={(o) => !o && setReceipt(null)}>
                <DialogContent dir="rtl" className="max-w-xl">
                    <DialogHeader className="pr-8 text-right">
                        <DialogTitle>رسید {receipt?.order}</DialogTitle>
                    </DialogHeader>
                    {receipt?.error ? (
                        <ErrorBox error={receipt.error} />
                    ) : receipt?.url ? (
                        <img src={receipt.url} alt="receipt" className="max-h-[70vh] w-full object-contain rounded-lg" />
                    ) : (
                        <Loading />
                    )}
                </DialogContent>
            </Dialog>

            <Dialog open={!!rejecting} onOpenChange={(o) => !o && setRejecting(null)}>
                <DialogContent dir="rtl">
                    <DialogHeader className="pr-8 text-right">
                        <DialogTitle>رد پرداخت {rejecting && money(rejecting.price)}</DialogTitle>
                    </DialogHeader>
                    <Field label="دلیل (برای کاربر فرستاده می‌شود)">
                        <Textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="رسید نامعتبر است" />
                    </Field>
                    <div className="flex justify-end gap-2">
                        <Button variant="outline" onClick={() => setRejecting(null)}>
                            انصراف
                        </Button>
                        <Button
                            variant="destructive"
                            disabled={act.busy || !reason.trim()}
                            onClick={async () => {
                                const p = rejecting
                                if (!p) return
                                setRejecting(null)
                                if (await act.run(() => api.post(`payments/${encodeURIComponent(p.id_order)}/reject`, { reason: reason.trim() }), 'پرداخت رد شد'))
                                    list.reload()
                            }}
                        >
                            رد پرداخت
                        </Button>
                    </div>
                </DialogContent>
            </Dialog>
        </div>
    )
}

function PaySettingsCard({ api }: { api: BotAPI }) {
    const s = useLoad(() => api.get<BotPaySettings>('payment-settings'), [api])
    if (!s.data) return s.error ? <ErrorBox error={s.error} /> : null
    return <PaySettingsForm api={api} orig={s.data} onSaved={s.setData} />
}

function PaySettingsForm({ api, orig, onSaved }: { api: BotAPI; orig: BotPaySettings; onSaved: (v: BotPaySettings) => void }) {
    const act = useAction()
    const [form, setForm] = useState<BotPaySettings>(() => ({ ...orig, enabled: { ...orig.enabled } }))
    const en = (k: string) => !!form.enabled[k]
    const setEn = (k: string, v: boolean) => setForm({ ...form, enabled: { ...form.enabled, [k]: v } })

    return (
        <Card>
            <CardHeader>
                <CardTitle>روش‌های پرداخت</CardTitle>
                <CardDescription>کدام روش‌ها در «افزایش موجودی» ربات نمایش داده شوند.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <Switch checked={en('card')} onChange={(v) => setEn('card', v)} label="کارت به کارت" />
                    <Switch checked={en('rial_gateway')} onChange={(v) => setEn('rial_gateway', v)} label="درگاه ریالی" />
                    <Switch checked={en('nowpayments')} onChange={(v) => setEn('nowpayments', v)} label="ارز دیجیتال (NOWPayments)" />
                    <Switch checked={en('aqayepardakht')} onChange={(v) => setEn('aqayepardakht', v)} label="آقای پرداخت" />
                </div>
                <Field label="متن کارت به کارت" hint="شماره کارت و نام صاحب حساب؛ همین متن به مشتری نشان داده می‌شود.">
                    <Textarea rows={4} value={form.card_text} onChange={(e) => setForm({ ...form, card_text: e.target.value })} />
                </Field>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <Field label="کلید API نوپیمنتس">
                        <Input dir="ltr" value={form.nowpayments_key} onChange={(e) => setForm({ ...form, nowpayments_key: e.target.value })} />
                    </Field>
                    <Field label="پین آقای پرداخت">
                        <Input dir="ltr" value={form.aqayepardakht_pin} onChange={(e) => setForm({ ...form, aqayepardakht_pin: e.target.value })} />
                    </Field>
                </div>
                <ErrorBox error={act.error} />
                <Notice text={act.notice} />
                <Button
                    disabled={act.busy}
                    onClick={async () => {
                        const r = await act.run(() => api.put<BotPaySettings>('payment-settings', form), 'ذخیره شد')
                        if (r && r !== true) onSaved(r)
                    }}
                >
                    {act.busy && <Spinner className="ml-2" />} ذخیره
                </Button>
            </CardContent>
        </Card>
    )
}
