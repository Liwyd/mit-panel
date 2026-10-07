import { useState } from 'react'
import { Search, Ban, CheckCircle2, Send, Wallet, ShieldCheck } from 'lucide-react'
import { BotAPI, BotPayment, BotService, BotUser, Paged } from '@/lib/bots-api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Empty, ErrorBox, Field, Loading, Notice, money, num, selectClass, useAction, useLoad, when } from './common'

const PAGE = 30
const onlyDigits = (v: string) => v.replace(/[۰-۹]/g, (d) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d))).replace(/[^\d]/g, '')

export function UsersTab({ api }: { api: BotAPI }) {
    const [q, setQ] = useState('')
    const [query, setQuery] = useState('')
    const [status, setStatus] = useState('')
    const [offset, setOffset] = useState(0)
    const [selected, setSelected] = useState<string | null>(null)
    const list = useLoad(
        () => api.get<Paged<BotUser>>('users', { q: query || undefined, status: status || undefined, limit: PAGE, offset }),
        [api, query, status, offset]
    )

    return (
        <div className="space-y-4">
            <Card>
                <CardHeader>
                    <CardTitle>کاربران</CardTitle>
                    <CardDescription>جستجو با آیدی عددی، یوزرنیم یا شماره تماس.</CardDescription>
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
                        <Input className="flex-1 min-w-[12rem]" value={q} onChange={(e) => setQ(e.target.value)} placeholder="آیدی، @یوزرنیم یا شماره" />
                        <select
                            className={selectClass + ' w-36'}
                            value={status}
                            onChange={(e) => {
                                setOffset(0)
                                setStatus(e.target.value)
                            }}
                        >
                            <option value="">همه</option>
                            <option value="Active">فعال</option>
                            <option value="block">مسدود</option>
                        </select>
                        <Button type="submit">
                            <Search className="h-4 w-4 ml-1" /> جستجو
                        </Button>
                    </form>
                    <ErrorBox error={list.error} />
                    {list.loading && !list.data ? (
                        <Loading />
                    ) : !list.data?.items.length ? (
                        <Empty text="کاربری پیدا نشد" />
                    ) : (
                        <div className="divide-y divide-border rounded-lg border border-border">
                            {list.data.items.map((u) => (
                                <button
                                    key={u.id}
                                    className="flex w-full flex-wrap items-center justify-between gap-2 p-3 text-right hover:bg-accent/50"
                                    onClick={() => setSelected(u.id)}
                                >
                                    <span className="flex items-center gap-2">
                                        <span className="font-mono text-sm" dir="ltr">
                                            {u.id}
                                        </span>
                                        {u.username && u.username !== 'NOT_USERNAME' && (
                                            <span className="text-sm text-muted-foreground" dir="ltr">
                                                @{u.username}
                                            </span>
                                        )}
                                        {u.User_Status === 'block' && <Badge variant="destructive">مسدود</Badge>}
                                    </span>
                                    <span className="text-sm">{money(u.Balance)}</span>
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
            <UserDialog api={api} id={selected} onClose={() => setSelected(null)} onChanged={list.reload} />
        </div>
    )
}

interface UserDetail {
    user: BotUser
    services: BotService[]
    payments: BotPayment[]
    paid_sum: number
}

function UserDialog({ api, id, onClose, onChanged }: { api: BotAPI; id: string | null; onClose: () => void; onChanged: () => void }) {
    const detail = useLoad(() => (id ? api.get<UserDetail>(`users/${id}`) : Promise.resolve(null)), [api, id])
    const act = useAction()
    const [amount, setAmount] = useState('')
    const [mode, setMode] = useState('add')
    const [text, setText] = useState('')
    const [blockReason, setBlockReason] = useState('')
    const [limit, setLimit] = useState('')

    const after = async (fn: () => Promise<unknown>, msg: string) => {
        if (await act.run(fn, msg)) {
            detail.reload()
            onChanged()
        }
    }
    const u = detail.data?.user

    return (
        <Dialog
            open={!!id}
            onOpenChange={(o) => {
                if (!o) {
                    act.setError(null)
                    act.setNotice(null)
                    onClose()
                }
            }}
        >
            <DialogContent dir="rtl" className="max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader className="pr-8 text-right">
                    <DialogTitle className="flex items-center gap-2">
                        کاربر <span dir="ltr">{id}</span>
                        {u?.User_Status === 'block' && <Badge variant="destructive">مسدود</Badge>}
                    </DialogTitle>
                </DialogHeader>
                {detail.loading && !u ? (
                    <Loading />
                ) : !u ? (
                    <ErrorBox error={detail.error} />
                ) : (
                    <div className="space-y-4 text-sm">
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                            <Info k="یوزرنیم" v={u.username && u.username !== 'NOT_USERNAME' ? '@' + u.username : '—'} ltr />
                            <Info k="شماره" v={u.number && u.number !== 'none' ? u.number : '—'} ltr />
                            <Info k="موجودی" v={money(u.Balance)} />
                            <Info k="جمع پرداخت‌ها" v={money(detail.data?.paid_sum)} />
                            <Info k="زیرمجموعه‌ها" v={num(u.affiliatescount)} />
                            <Info k="آخرین پیام" v={when(u.last_message_time)} />
                        </div>
                        {u.User_Status === 'block' && u.description_blocking && <p className="text-destructive">دلیل مسدودی: {u.description_blocking}</p>}

                        <ErrorBox error={act.error} />
                        <Notice text={act.notice} />

                        <div className="rounded-lg border border-border p-3 space-y-2">
                            <div className="font-medium flex items-center gap-2">
                                <Wallet className="h-4 w-4" /> موجودی
                            </div>
                            <div className="flex flex-wrap gap-2">
                                <select className={selectClass + ' w-32'} value={mode} onChange={(e) => setMode(e.target.value)}>
                                    <option value="add">افزودن</option>
                                    <option value="sub">کسر</option>
                                    <option value="set">تنظیم روی</option>
                                </select>
                                <Input className="w-40" dir="ltr" inputMode="numeric" value={amount} onChange={(e) => setAmount(onlyDigits(e.target.value))} placeholder="تومان" />
                                <Button
                                    disabled={act.busy || !amount}
                                    onClick={() => after(() => api.post(`users/${id}/balance`, { amount, mode }), 'موجودی به‌روز شد')}
                                >
                                    اعمال
                                </Button>
                            </div>
                        </div>

                        <div className="rounded-lg border border-border p-3 space-y-2">
                            <div className="font-medium flex items-center gap-2">
                                <Send className="h-4 w-4" /> پیام به کاربر
                            </div>
                            <Textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} />
                            <Button
                                disabled={act.busy || !text.trim()}
                                onClick={async () => {
                                    if (await act.run(() => api.post(`users/${id}/message`, { text }), 'پیام فرستاده شد')) setText('')
                                }}
                            >
                                ارسال
                            </Button>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <div className="rounded-lg border border-border p-3 space-y-2">
                                {u.User_Status === 'block' ? (
                                    <Button variant="outline" disabled={act.busy} onClick={() => after(() => api.post(`users/${id}/unblock`), 'کاربر آزاد شد')}>
                                        <CheckCircle2 className="h-4 w-4 ml-1" /> رفع مسدودی
                                    </Button>
                                ) : (
                                    <>
                                        <Input value={blockReason} onChange={(e) => setBlockReason(e.target.value)} placeholder="دلیل مسدودی" />
                                        <Button
                                            variant="destructive"
                                            disabled={act.busy}
                                            onClick={() => after(() => api.post(`users/${id}/block`, { reason: blockReason }), 'کاربر مسدود شد')}
                                        >
                                            <Ban className="h-4 w-4 ml-1" /> مسدود کردن
                                        </Button>
                                    </>
                                )}
                            </div>
                            <div className="rounded-lg border border-border p-3 space-y-2">
                                <Field label={`سقف اکانت تست (الان ${u.limit_usertest})`}>
                                    <div className="flex gap-2">
                                        <Input dir="ltr" inputMode="numeric" value={limit} onChange={(e) => setLimit(onlyDigits(e.target.value))} />
                                        <Button variant="outline" disabled={act.busy || !limit} onClick={() => after(() => api.post(`users/${id}/test-limit`, { limit }), 'ذخیره شد')}>
                                            ثبت
                                        </Button>
                                    </div>
                                </Field>
                                {u.verify !== '1' && (
                                    <Button variant="outline" disabled={act.busy} onClick={() => after(() => api.post(`users/${id}/verify`), 'کاربر احراز شد')}>
                                        <ShieldCheck className="h-4 w-4 ml-1" /> احراز هویت
                                    </Button>
                                )}
                            </div>
                        </div>

                        <div>
                            <div className="font-medium mb-2">سرویس‌ها ({detail.data?.services.length || 0})</div>
                            {detail.data?.services.length ? (
                                <div className="divide-y divide-border rounded-lg border border-border">
                                    {detail.data.services.map((s) => (
                                        <div key={s.id_invoice} className="flex flex-wrap justify-between gap-2 p-2">
                                            <span dir="ltr" className="font-mono">
                                                {s.username}
                                            </span>
                                            <span className="text-muted-foreground">
                                                {s.name_product} · {s.Service_location} · {s.Status}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <p className="text-muted-foreground">سرویسی ندارد</p>
                            )}
                        </div>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    )
}

function Info({ k, v, ltr }: { k: string; v: React.ReactNode; ltr?: boolean }) {
    return (
        <div className="rounded-lg bg-muted/40 p-2">
            <div className="text-xs text-muted-foreground">{k}</div>
            <div className="font-medium truncate" dir={ltr ? 'ltr' : undefined}>
                {v}
            </div>
        </div>
    )
}
