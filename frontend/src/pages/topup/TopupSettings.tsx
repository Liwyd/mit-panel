import { useState } from 'react'
import { BotAPI, TopupSettings as Settings } from '@/lib/bots-api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBox, Field, Loading, Notice, Spinner, Switch, num, useAction, useLoad } from '../bots/common'

export function TopupSettings({ api }: { api: BotAPI }) {
    const remote = useLoad(() => api.get<Settings>('settings'), [api])
    if (remote.loading && !remote.data) return <Loading />
    if (!remote.data) return <ErrorBox error={remote.error} />
    return <Editor api={api} d={remote.data} onSaved={remote.setData} />
}

function Editor({ api, d, onSaved }: { api: BotAPI; d: Settings; onSaved: (s: Settings) => void }) {
    const [price, setPrice] = useState(d.price_per_gb ? String(d.price_per_gb) : '')
    const [card, setCard] = useState(d.card_number)
    const [joinOn, setJoinOn] = useState(d.force_join_enabled)
    const [channel, setChannel] = useState(d.force_join_channel)
    const [autoApprove, setAutoApprove] = useState(d.auto_approve_enabled)
    const [pin, setPin] = useState('')
    const act = useAction()

    const body: Record<string, string | boolean> = {}
    if (price.trim() && Number(price.replace(/,/g, '')) !== d.price_per_gb) body.price_per_gb = price
    if (card !== d.card_number) body.card_number = card
    if (channel !== d.force_join_channel) body.force_join_channel = channel
    if (joinOn !== d.force_join_enabled) body.force_join_enabled = joinOn
    if (autoApprove !== d.auto_approve_enabled) body.auto_approve_enabled = autoApprove
    if (pin.trim()) body.bulk_password_pin = pin
    const changes = Object.keys(body).length

    return (
        <Card>
            <CardHeader>
                <CardTitle>تنظیمات ربات</CardTitle>
                <CardDescription>همان تنظیمات بخش «تنظیمات» منوی سوپرادمین در خود ربات؛ از هر کدام عوض شود، هر دو یکی است.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                    <Field label="قیمت هر گیگابایت (تومان)" hint={`هر خرید بین ${num(d.min_gb)} تا ${num(d.max_gb)} گیگابایت است (از .env ربات).`}>
                        <Input dir="ltr" inputMode="numeric" value={price} onChange={(e) => setPrice(e.target.value)} />
                    </Field>
                    <Field label="شماره کارت" hint="برای کارت به کارت، شارژ کیف پول و پرداخت فاکتورها نشان داده می‌شود.">
                        <Input dir="ltr" value={card} onChange={(e) => setCard(e.target.value)} />
                    </Field>
                </div>
                <Switch
                    checked={autoApprove}
                    onChange={setAutoApprove}
                    label="تأیید خودکار رسیدها"
                    hint="هر رسید یک دقیقه بعد بدون بررسی تأیید می‌شود، مگر اینکه در همان یک دقیقه «رد» را بزنید."
                />
                <Switch checked={joinOn} onChange={setJoinOn} label="عضویت اجباری در کانال" hint="ربات باید ادمین کانال باشد، وگرنه همه بدون عضویت رد می‌شوند." />
                <Field label="کانال عضویت اجباری">
                    <Input dir="ltr" value={channel} placeholder="@channel" onChange={(e) => setChannel(e.target.value)} />
                </Field>
                <Field
                    label="رمز خروجی گرفتن از همه‌ی رمزها"
                    hint={d.has_bulk_pin ? 'یک رمز تنظیم شده است؛ برای عوض کردن، رمز تازه را بنویسید.' : 'هنوز تنظیم نشده؛ بدون آن «خروجی همه‌ی رمزها» در ربات کار نمی‌کند.'}
                >
                    <Input dir="ltr" type="password" value={pin} onChange={(e) => setPin(e.target.value)} />
                </Field>
                <ErrorBox error={act.error} />
                <Notice text={act.notice} />
                <Button
                    disabled={act.busy || !changes}
                    onClick={async () => {
                        const res = await act.run(() => api.put<Settings>('settings', body), 'ذخیره شد')
                        if (res && res !== true) {
                            onSaved(res as Settings)
                            setPin('')
                        }
                    }}
                >
                    {act.busy && <Spinner className="ml-2" />} ذخیره {changes ? `(${changes})` : ''}
                </Button>
            </CardContent>
        </Card>
    )
}
