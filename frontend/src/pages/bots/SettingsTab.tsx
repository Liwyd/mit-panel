import { useState } from 'react'
import { BotAffiliates, BotAPI, BotSettings } from '@/lib/bots-api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBox, Field, Loading, Notice, Spinner, Switch, useAction, useLoad } from './common'

const FLAGS: Array<[keyof BotSettings, string, string?]> = [
    ['Bot_Status', 'ربات روشن است', 'خاموش که باشد، فقط ادمین‌ها می‌توانند از ربات استفاده کنند.'],
    ['roll_Status', 'بخش قوانین', 'کاربر جدید باید قوانین را بپذیرد.'],
    ['get_number', 'احراز هویت شماره', 'قبل از خرید، شماره تماس کاربر گرفته می‌شود.'],
    ['iran_number', 'فقط شماره ایران 🇮🇷'],
    ['status_verify', 'احراز هویت دستی', 'کاربر جدید تا تأیید ادمین نمی‌تواند از ربات استفاده کند.'],
    ['NotUser', 'دکمه «نام کاربری من در لیست نیست»', 'کاربر می‌تواند سرویسی را که بیرون از ربات گرفته، با نام کاربری‌اش به لیست خودش اضافه کند.'],
    ['help_Status', 'بخش آموزش'],
    ['statuscategory', 'دسته‌بندی محصولات', 'مشتری اول دسته را انتخاب می‌کند.'],
    ['copy_cart', 'دکمه‌ی کپی شماره کارت'],
]
const VALUES: Array<[keyof BotSettings, string, string?]> = [
    ['time_usertest', 'مدت اکانت تست (ساعت)'],
    ['val_usertest', 'حجم اکانت تست (مگابایت)', 'حداقل ۱۰۰'],
    ['limit_usertest_all', 'سقف اکانت تست هر کاربر'],
    ['Extra_volume', 'قیمت هر گیگ حجم اضافه (تومان)'],
    ['removedayc', 'حذف سرویس‌های منقضی بعد از (روز)'],
    ['Channel_Report', 'آیدی کانال گزارش', 'مثل -1001234567890'],
]
const CRONS: Array<[string, string, string]> = [
    ['test', 'حذف اکانت‌های تست تمام‌شده', 'هر ۱۵ دقیقه'],
    ['volume', 'هشدار پایان حجم', 'هر دقیقه'],
    ['time', 'هشدار پایان زمان', 'هر دقیقه'],
    ['remove', 'حذف سرویس‌های منقضی', 'هر دقیقه'],
    ['card', 'تأیید خودکار رسیدها بدون بررسی', 'هر ۴ دقیقه همه‌ی رسیدهای کارت به کارتِ در انتظار، بدون بررسی شما تأیید می‌شوند. با «تأیید خودکار پرداخت» (اپ پیامک) فرق دارد.'],
]

export function SettingsTab({ api }: { api: BotAPI }) {
    const remote = useLoad(() => api.get<BotSettings>('settings'), [api])
    if (remote.loading && !remote.data) return <Loading />
    if (!remote.data) return <ErrorBox error={remote.error} />
    return (
        <div className="space-y-4">
            {/* the form starts from the first load; after a save orig follows the bot */}
            <SettingsForm api={api} orig={remote.data} onSaved={remote.setData} />
            <AffiliatesCard api={api} />
        </div>
    )
}

function SettingsForm({ api, orig, onSaved }: { api: BotAPI; orig: BotSettings; onSaved: (s: BotSettings) => void }) {
    const [form, setForm] = useState<BotSettings>(() => JSON.parse(JSON.stringify(orig)))
    const act = useAction()

    const save = async () => {
        const body: Record<string, unknown> = {}
        for (const [k] of [...FLAGS, ...VALUES]) {
            if (form[k] !== orig[k]) body[k] = form[k]
        }
        if (form.channel !== orig.channel) body.channel = form.channel
        const crons: Record<string, boolean> = {}
        for (const [k] of CRONS) if (form.crons[k] !== orig.crons[k]) crons[k] = form.crons[k]
        if (Object.keys(crons).length) body.crons = crons
        const r = await act.run(() => api.put<BotSettings>('settings', body), 'ذخیره شد')
        if (r && r !== true) onSaved(r)
    }

    return (
        <>
            <Card>
                <CardHeader>
                    <CardTitle>قابلیت‌ها</CardTitle>
                </CardHeader>
                <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {FLAGS.map(([k, label, hint]) => (
                        <Switch key={k} checked={!!form[k]} onChange={(v) => setForm({ ...form, [k]: v })} label={label} hint={hint} />
                    ))}
                </CardContent>
            </Card>
            <Card>
                <CardHeader>
                    <CardTitle>مقادیر</CardTitle>
                </CardHeader>
                <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {VALUES.map(([k, label, hint]) => (
                        <Field key={k} label={label} hint={hint}>
                            <Input dir="ltr" value={String(form[k] ?? '')} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
                        </Field>
                    ))}
                    <Field label="کانال عضویت اجباری" hint="یوزرنیم کانال بدون @؛ خالی یعنی بدون عضویت اجباری. ربات باید ادمین کانال باشد.">
                        <Input dir="ltr" value={form.channel} onChange={(e) => setForm({ ...form, channel: e.target.value })} />
                    </Field>
                </CardContent>
            </Card>
            <Card>
                <CardHeader>
                    <CardTitle>کارهای خودکار</CardTitle>
                    <CardDescription>داخل خود ربات اجرا می‌شوند و دیگر به crontab سرور نیازی نیست.</CardDescription>
                </CardHeader>
                <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {CRONS.map(([k, label, hint]) => (
                        <Switch
                            key={k}
                            checked={!!form.crons[k]}
                            onChange={(v) => setForm({ ...form, crons: { ...form.crons, [k]: v } })}
                            label={label}
                            hint={hint}
                        />
                    ))}
                </CardContent>
            </Card>
            <div className="space-y-2">
                <ErrorBox error={act.error} />
                <Notice text={act.notice} />
                <div className="flex gap-2">
                    <Button onClick={save} disabled={act.busy}>
                        {act.busy && <Spinner className="ml-2" />} ذخیره تنظیمات
                    </Button>
                    <Button variant="outline" onClick={() => setForm(JSON.parse(JSON.stringify(orig)))}>
                        برگرداندن
                    </Button>
                </div>
            </div>
        </>
    )
}

function AffiliatesCard({ api }: { api: BotAPI }) {
    const remote = useLoad(() => api.get<BotAffiliates>('affiliates'), [api])
    if (!remote.data) return remote.error ? <ErrorBox error={remote.error} /> : null
    return <AffiliatesForm api={api} orig={remote.data} onSaved={remote.setData} />
}

function AffiliatesForm({ api, orig, onSaved }: { api: BotAPI; orig: BotAffiliates; onSaved: (a: BotAffiliates) => void }) {
    const [form, setForm] = useState<BotAffiliates>(() => ({ ...orig }))
    const act = useAction()

    return (
        <Card>
            <CardHeader>
                <CardTitle>زیرمجموعه‌گیری</CardTitle>
                <CardDescription>هر کاربر با لینک دعوتش، از خرید زیرمجموعه‌ها پورسانت می‌گیرد.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <Switch checked={form.enabled} onChange={(v) => setForm({ ...form, enabled: v })} label="فعال" />
                    <Switch checked={form.commission} onChange={(v) => setForm({ ...form, commission: v })} label="پورسانت از خرید" />
                    <Switch checked={form.start_gift} onChange={(v) => setForm({ ...form, start_gift: v })} label="هدیه‌ی عضویت" />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <Field label="درصد پورسانت">
                        <Input dir="ltr" value={form.percent} onChange={(e) => setForm({ ...form, percent: e.target.value.replace(/[^\d]/g, '') })} />
                    </Field>
                    <Field label="مبلغ هدیه‌ی عضویت (تومان)">
                        <Input dir="ltr" value={form.start_gift_amount} onChange={(e) => setForm({ ...form, start_gift_amount: e.target.value.replace(/[^\d]/g, '') })} />
                    </Field>
                </div>
                <Field label="توضیح بخش زیرمجموعه">
                    <Textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
                </Field>
                <ErrorBox error={act.error} />
                <Notice text={act.notice} />
                <Button
                    disabled={act.busy}
                    onClick={async () => {
                        const r = await act.run(
                            () =>
                                api.put<BotAffiliates>('affiliates', {
                                    enabled: form.enabled,
                                    commission: form.commission,
                                    start_gift: form.start_gift,
                                    percent: form.percent || '0',
                                    start_gift_amount: form.start_gift_amount || '0',
                                    description: form.description,
                                }),
                            'ذخیره شد'
                        )
                        if (r && r !== true) onSaved(r)
                    }}
                >
                    {act.busy && <Spinner className="ml-2" />} ذخیره
                </Button>
            </CardContent>
        </Card>
    )
}
