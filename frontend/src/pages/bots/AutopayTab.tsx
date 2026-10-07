import { useRef, useState } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { Copy, Download, KeyRound, Smartphone, Upload, Github, RefreshCw } from 'lucide-react'
import { BotAPI, BotAutopay, botsAPI } from '@/lib/bots-api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Empty, ErrorBox, Loading, Notice, Spinner, money, useAction, useLoad } from './common'

const MODES: Array<{ v: BotAutopay['mode']; title: string; hint: string; badge?: string }> = [
    { v: 'off', title: 'خاموش (بررسی دستی)', hint: 'هر رسید را خودتان در ربات یا در «پرداخت‌ها» تأیید یا رد می‌کنید.' },
    {
        v: 'no_review',
        title: 'تأیید خودکار بدون بررسی',
        hint: 'هر رسید کارت به کارت حدود یک دقیقه بعد از ارسال، بدون بررسی تأیید و شارژ می‌شود و رسید برای شما فرستاده می‌شود تا خودتان هم بررسی کنید. سریع است، ولی رسید جعلی هم تأیید می‌شود.',
    },
    {
        v: 'sms',
        title: 'تأیید خودکار با بررسی واقعی پیامک‌ها',
        badge: 'نسخه آزمایشی',
        hint: 'اپ اندروید پیامک واریز بانک را می‌خواند و فقط وقتی همان مبلغ واقعاً به حساب نشسته باشد، شارژ می‌کند. به یک گوشی اندرویدی که پیامک‌های بانک به آن می‌آید نیاز دارد.',
    },
]

const SMS_STATUS: Record<string, string> = {
    matched: 'شارژ شد',
    new: 'در حال بررسی',
    unmatched: 'سفارشی با این مبلغ نبود',
    ignored: 'واریز نبود',
    unreadable: 'خوانده نشد',
    skipped: 'قبلاً بررسی شده',
}

function size(bytes: number): string {
    return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`
}

function lastSeen(v: string): { text: string; ok: boolean } {
    if (!v) return { text: 'هنوز وصل نشده', ok: false }
    const t = Date.parse(v.replace(' ', 'T') + '+03:30')
    if (isNaN(t)) return { text: v, ok: true }
    const mins = Math.round((Date.now() - t) / 60000)
    if (mins < 2) return { text: 'همین الان', ok: true }
    if (mins < 60) return { text: `${mins} دقیقه پیش`, ok: mins < 15 }
    const h = Math.round(mins / 60)
    if (h < 48) return { text: `${h} ساعت پیش`, ok: false }
    return { text: `${Math.round(h / 24)} روز پیش`, ok: false }
}

export function AutopayTab({ api, superadmin }: { api: BotAPI; superadmin: boolean }) {
    const remote = useLoad(() => api.get<BotAutopay>('autopay'), [api])
    const apk = useLoad(() => botsAPI.apkInfo(), [])
    const act = useAction()
    const [showPairing, setShowPairing] = useState(false)
    const fileRef = useRef<HTMLInputElement>(null)

    if (remote.loading && !remote.data) return <Loading />
    if (!remote.data) return <ErrorBox error={remote.error} />
    const a = remote.data
    const seen = lastSeen(a.last_seen)

    return (
        <div className="space-y-4">
            <ErrorBox error={act.error} />
            <Notice text={act.notice} />
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Smartphone className="h-5 w-5 text-primary" /> تأیید خودکار پرداخت
                    </CardTitle>
                    <CardDescription className="leading-6">رسیدهای کارت به کارت چطور تأیید شوند؟ فقط یکی از این‌ها در هر زمان فعال است.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                    {MODES.map((m) => (
                        <button
                            key={m.v}
                            disabled={act.busy}
                            onClick={async () => {
                                if (m.v === a.mode) return
                                if (m.v === 'no_review' && !confirm('در این حالت هر رسیدی، حتی رسید جعلی، حدود یک دقیقه بعد تأیید می‌شود. فعال شود؟')) return
                                const r = await act.run(() => api.put<BotAutopay>('autopay', { mode: m.v }), 'ذخیره شد')
                                if (r && r !== true) remote.setData(r)
                            }}
                            className={
                                'flex w-full items-start gap-3 rounded-xl border p-3 text-right transition ' +
                                (a.mode === m.v ? 'border-primary bg-primary/5 ring-1 ring-primary' : 'border-border hover:bg-accent/40')
                            }
                        >
                            <span
                                className={
                                    'mt-1 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 ' +
                                    (a.mode === m.v ? 'border-primary' : 'border-muted-foreground/40')
                                }
                            >
                                {a.mode === m.v && <span className="h-2 w-2 rounded-full bg-primary" />}
                            </span>
                            <span className="space-y-0.5">
                                <span className="flex flex-wrap items-center gap-2 font-semibold">
                                    {m.title}
                                    {m.badge && <Badge variant="gold">{m.badge}</Badge>}
                                </span>
                                <span className="block text-xs leading-6 text-muted-foreground">{m.hint}</span>
                            </span>
                        </button>
                    ))}
                    {a.mode === 'sms' && (
                        <div className="grid grid-cols-2 gap-3 pt-1 text-sm md:grid-cols-4">
                            <div className="rounded-lg bg-muted/40 p-3">
                                <div className="text-xs text-muted-foreground">آخرین ارتباط گوشی</div>
                                <div className="flex items-center gap-1 font-medium">
                                    {seen.text} <Badge variant={seen.ok ? 'success' : 'secondary'}>{seen.ok ? 'وصل' : 'قطع'}</Badge>
                                </div>
                            </div>
                            <div className="rounded-lg bg-muted/40 p-3">
                                <div className="text-xs text-muted-foreground">گوشی</div>
                                <div className="truncate font-medium" dir="ltr">
                                    {a.device || '—'}
                                </div>
                            </div>
                            <div className="rounded-lg bg-muted/40 p-3">
                                <div className="text-xs text-muted-foreground">پرداخت‌های خودکار</div>
                                <div className="font-medium">{a.paid_count}</div>
                            </div>
                            <div className="rounded-lg bg-muted/40 p-3">
                                <div className="text-xs text-muted-foreground">در انتظار واریز</div>
                                <div className="font-medium">{a.open_count}</div>
                            </div>
                        </div>
                    )}
                </CardContent>
            </Card>

            {a.mode === 'sms' && (
                <>
            <Card>
                <CardHeader>
                    <CardTitle className="flex flex-wrap items-center gap-2">
                        نصب و اتصال اپ <Badge variant="gold">نسخه آزمایشی</Badge>
                    </CardTitle>
                    <CardDescription className="leading-6">
                        اپ اندروید «تأیید خودکار MIT» هنوز آزمایشی است. چند روز اول، شارژهای خودکار را با پیامک‌های بانک هم مقایسه کنید و اگر
                        پیامکی تشخیص داده نشد، از بخش «آخرین پیامک‌ها» همین صفحه ببینید چه رسیده است.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3 text-sm leading-7">
                    <GuideStep n={1} title="دانلود اپ">
                        <p>روی گوشی‌ای که پیامک‌های واریز بانک به آن می‌رسد، همین صفحه را باز کنید و اپ را بگیرید.</p>
                        <div className="flex flex-wrap items-center gap-2">
                            <Button disabled={!apk.data?.available || act.busy} onClick={() => act.run(() => botsAPI.apkDownload())}>
                                <Download className="h-4 w-4 ml-1" /> دانلود اپ اندروید (آزمایشی)
                            </Button>
                            {apk.data?.available ? (
                                <span className="text-xs text-muted-foreground">
                                    {apk.data.version ? `نسخه ${apk.data.version} · ` : ''}
                                    {apk.data.size ? size(apk.data.size) : ''}
                                </span>
                            ) : (
                                <span className="text-xs text-muted-foreground">
                                    {superadmin ? 'هنوز فایلی بارگذاری نشده (پایین همین بخش).' : 'هنوز فایلی بارگذاری نشده؛ به مدیر پنل اطلاع دهید.'}
                                </span>
                            )}
                        </div>
                    </GuideStep>
                    <GuideStep n={2} title="نصب">
                        <p>
                            فایل <code dir="ltr">mit-autopay.apk</code> را باز کنید. اگر اندروید پرسید، «اجازه‌ی نصب از این منبع» را بدهید (چون اپ از
                            گوگل‌پلی نصب نمی‌شود). اگر نسخه‌ی قبلی را دارید و نصب خطا داد، اول آن را حذف کنید.
                        </p>
                    </GuideStep>
                    <GuideStep n={3} title="اجازه‌ها">
                        <p>
                            وقتی اپ اجازه‌ی <b>دریافت و خواندن پیامک</b> خواست، قبول کنید. بعد دکمه‌ی <b>«اجازه‌ی اجرای دائمی (بهینه‌سازی باتری)»</b> را
                            در اپ بزنید و «اجازه» را انتخاب کنید تا اندروید اپ را در پس‌زمینه نبندد.
                        </p>
                    </GuideStep>
                    <GuideStep n={4} title="اتصال به این ربات">
                        <p>
                            «نمایش کد» را بزنید. کد را کپی کنید (یا QR را با دوربین گوشی اسکن کنید تا متنش را بگیرید)، در کادر اپ جای‌گذاری کنید و{' '}
                            <b>«اتصال به بات»</b> را بزنید.
                        </p>
                        <div className="rounded-xl border border-border p-3 space-y-3">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                                <b>کد اتصال این ربات</b>
                                <Button size="sm" variant="outline" onClick={() => setShowPairing((v) => !v)}>
                                    {showPairing ? 'پنهان کردن' : 'نمایش کد'}
                                </Button>
                            </div>
                            <p className="text-xs text-muted-foreground">این کد مثل رمز است؛ هر کس داشته باشد می‌تواند برای ربات پیامک واریز بفرستد.</p>
                            {showPairing && (
                                <div className="flex flex-col items-center gap-3">
                                    <div className="rounded-xl bg-white p-3">
                                        <QRCodeSVG value={a.pairing} size={200} />
                                    </div>
                                    <div className="flex w-full items-center gap-2">
                                        <code className="flex-1 break-all rounded-lg bg-muted/50 p-2 text-xs" dir="ltr">
                                            {a.pairing}
                                        </code>
                                        <Button
                                            size="icon"
                                            variant="outline"
                                            onClick={() => {
                                                navigator.clipboard?.writeText(a.pairing)
                                                act.setNotice('کد کپی شد')
                                            }}
                                            aria-label="کپی"
                                        >
                                            <Copy className="h-4 w-4" />
                                        </Button>
                                    </div>
                                </div>
                            )}
                            <Button
                                size="sm"
                                variant="outline"
                                className="h-auto min-h-9 whitespace-normal text-right"
                                disabled={act.busy}
                                onClick={async () => {
                                    if (!confirm('کلید جدید ساخته شود؟ گوشی فعلی قطع می‌شود و باید دوباره کد را در اپ بزند.')) return
                                    const r = await act.run(() => api.post<BotAutopay>('autopay/new-key'), 'کلید جدید ساخته شد؛ کد را دوباره در اپ بزنید')
                                    if (r && r !== true) remote.setData(r)
                                }}
                            >
                                {act.busy ? <Spinner className="ml-1" /> : <KeyRound className="h-4 w-4 ml-1" />} ساخت کلید جدید (اگر گوشی عوض شد)
                            </Button>
                        </div>
                    </GuideStep>
                    <GuideStep n={5} title="آزمایش" done={seen.ok}>
                        <p>
                            در اپ <b>«تست ارتباط با سرور»</b> را بزنید و این‌جا «بارگذاری دوباره» را بزنید. «آخرین ارتباط گوشی» باید «همین الان» شود.
                        </p>
                        <div className="flex flex-wrap items-center gap-2">
                            <Badge variant={seen.ok ? 'success' : 'secondary'}>
                                {seen.ok ? 'گوشی وصل است' : 'هنوز وصل نیست'} · {seen.text}
                            </Badge>
                            <Button size="sm" variant="outline" onClick={remote.reload}>
                                <RefreshCw className="h-4 w-4 ml-1" /> بارگذاری دوباره
                            </Button>
                        </div>
                        <p className="text-xs text-muted-foreground">
                            از این به بعد کارت به کارت‌ها با رسیدن پیامک بانک خودکار شارژ می‌شوند (گزینه‌ی «با بررسی واقعی پیامک‌ها» بالای همین صفحه).
                        </p>
                    </GuideStep>
                    <GuideStep n={6} title="اختیاری: فقط پیامک‌های بانک">
                        <p>
                            اگر روی این گوشی پیامک‌های دیگر هم می‌آید، در کادر «فقط پیامک این فرستنده‌ها» نام یا شماره‌ی فرستنده‌ی بانک را بنویسید و
                            «ذخیره‌ی فیلتر فرستنده» را بزنید. با «بازبینی پیامک‌های ۲۴ ساعت اخیر» پیامک‌های جامانده هم دوباره فرستاده می‌شوند.
                        </p>
                    </GuideStep>

                    {superadmin && (
                        <div className="flex flex-wrap gap-2 rounded-lg border border-dashed border-border p-3">
                            <span className="w-full text-xs text-muted-foreground">فقط شما: فایل اپ برای همه‌ی ادمین‌ها</span>
                            <Button
                                size="sm"
                                variant="outline"
                                disabled={act.busy}
                                onClick={async () => {
                                    if (await act.run(() => botsAPI.apkFetch(), 'آخرین نسخه از GitHub گرفته شد')) apk.reload()
                                }}
                            >
                                <Github className="h-4 w-4 ml-1" /> گرفتن آخرین نسخه از GitHub
                            </Button>
                            <Button size="sm" variant="outline" disabled={act.busy} onClick={() => fileRef.current?.click()}>
                                <Upload className="h-4 w-4 ml-1" /> بارگذاری فایل APK
                            </Button>
                            <input
                                ref={fileRef}
                                type="file"
                                accept=".apk,application/vnd.android.package-archive"
                                className="hidden"
                                onChange={async (e) => {
                                    const f = e.target.files?.[0]
                                    e.target.value = ''
                                    if (f && (await act.run(() => botsAPI.apkUpload(f), 'اپ بارگذاری شد'))) apk.reload()
                                }}
                            />
                        </div>
                    )}
                </CardContent>
            </Card>

                </>
            )}

            {a.mode === 'sms' && (
            <Card>
                <CardHeader>
                    <CardTitle>آخرین پیامک‌ها</CardTitle>
                </CardHeader>
                <CardContent>
                    {!a.recent_sms.length ? (
                        <Empty text="هنوز پیامکی نرسیده" />
                    ) : (
                        <div className="overflow-x-auto">
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead className="text-right">فرستنده</TableHead>
                                        <TableHead className="text-right">مبلغ</TableHead>
                                        <TableHead className="text-right">زمان</TableHead>
                                        <TableHead className="text-right">نتیجه</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {a.recent_sms.map((s) => (
                                        <TableRow key={s.id}>
                                            <TableCell dir="ltr" className="text-right">
                                                {s.sender}
                                            </TableCell>
                                            <TableCell>{s.amount ? money(s.amount) : '—'}</TableCell>
                                            <TableCell dir="ltr" className="text-right text-xs">
                                                {s.sent_at || s.received_at}
                                            </TableCell>
                                            <TableCell>
                                                <Badge variant={s.status === 'matched' ? 'success' : 'secondary'}>{SMS_STATUS[s.status] || s.status}</Badge>
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </div>
                    )}
                </CardContent>
            </Card>
            )}
        </div>
    )
}

function GuideStep({ n, title, done, children }: { n: number; title: string; done?: boolean; children: React.ReactNode }) {
    return (
        <div className="flex gap-3 rounded-xl border border-border p-3">
            <span
                className={
                    'flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ' +
                    (done ? 'bg-brand-green text-white' : 'bg-primary text-primary-foreground')
                }
            >
                {done ? '✓' : n.toLocaleString('fa-IR')}
            </span>
            <div className="min-w-0 flex-1 space-y-2">
                <b className="block">{title}</b>
                {children}
            </div>
        </div>
    )
}
