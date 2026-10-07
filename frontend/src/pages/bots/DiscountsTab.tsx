import { useState } from 'react'
import { Trash2, Plus } from 'lucide-react'
import { BotAPI, BotDiscount, BotGiftCode } from '@/lib/bots-api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Empty, ErrorBox, Field, Loading, Switch, money, num, useAction, useLoad } from './common'

const onlyDigits = (v: string) => v.replace(/[۰-۹]/g, (d) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d))).replace(/[^\d]/g, '')

export function DiscountsTab({ api }: { api: BotAPI }) {
    const discounts = useLoad(() => api.get<BotDiscount[]>('discounts'), [api])
    const gifts = useLoad(() => api.get<BotGiftCode[]>('giftcodes'), [api])
    const act = useAction()
    const [d, setD] = useState({ code: '', percent: '', limit: '', first_purchase_only: false })
    const [g, setG] = useState({ code: '', price: '' })

    if (discounts.loading && !discounts.data) return <Loading />

    return (
        <div className="space-y-4">
            <ErrorBox error={act.error || discounts.error || gifts.error} />

            <Card>
                <CardHeader>
                    <CardTitle>کد تخفیف خرید</CardTitle>
                    <CardDescription>درصدی از قیمت سرویس کم می‌کند. مشتری موقع پیش‌فاکتور دکمه‌ی «ثبت کد تخفیف» را می‌زند.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 items-end">
                        <Field label="کد (حروف و عدد انگلیسی)">
                            <Input dir="ltr" value={d.code} onChange={(e) => setD({ ...d, code: e.target.value.replace(/[^A-Za-z0-9]/g, '') })} placeholder="OFF20" />
                        </Field>
                        <Field label="درصد">
                            <Input dir="ltr" inputMode="numeric" value={d.percent} onChange={(e) => setD({ ...d, percent: onlyDigits(e.target.value) })} placeholder="20" />
                        </Field>
                        <Field label="تعداد دفعات استفاده">
                            <Input dir="ltr" inputMode="numeric" value={d.limit} onChange={(e) => setD({ ...d, limit: onlyDigits(e.target.value) })} placeholder="100" />
                        </Field>
                        <Button
                            disabled={act.busy || !d.code || !d.percent || !d.limit}
                            onClick={async () => {
                                const r = await act.run(() => api.post<BotDiscount[]>('discounts', d))
                                if (r && r !== true) {
                                    discounts.setData(r)
                                    setD({ code: '', percent: '', limit: '', first_purchase_only: false })
                                }
                            }}
                        >
                            <Plus className="h-4 w-4 ml-1" /> ساخت
                        </Button>
                    </div>
                    <Switch
                        checked={d.first_purchase_only}
                        onChange={(v) => setD({ ...d, first_purchase_only: v })}
                        label="فقط برای خرید اول"
                        hint="مشتری‌ای که قبلاً سرویس خریده نمی‌تواند از این کد استفاده کند."
                    />
                    {!discounts.data?.length ? (
                        <Empty text="کد تخفیفی نیست" />
                    ) : (
                        <div className="overflow-x-auto">
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead className="text-right">کد</TableHead>
                                        <TableHead className="text-right">درصد</TableHead>
                                        <TableHead className="text-right">استفاده‌شده</TableHead>
                                        <TableHead className="text-right">خرید اول</TableHead>
                                        <TableHead></TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {discounts.data.map((x) => (
                                        <TableRow key={x.id}>
                                            <TableCell dir="ltr" className="text-right font-mono">{x.codeDiscount}</TableCell>
                                            <TableCell>{x.price}٪</TableCell>
                                            <TableCell>
                                                {num(x.usedDiscount)} / {num(x.limitDiscount)}
                                            </TableCell>
                                            <TableCell>{x.usefirst === '1' ? 'بله' : 'خیر'}</TableCell>
                                            <TableCell className="text-left">
                                                <Button
                                                    size="xs"
                                                    variant="ghost"
                                                    onClick={async () => {
                                                        if (!confirm(`کد ${x.codeDiscount} حذف شود؟`)) return
                                                        if (await act.run(() => api.del(`discounts/${x.id}`))) discounts.reload()
                                                    }}
                                                >
                                                    <Trash2 className="h-4 w-4 text-destructive" />
                                                </Button>
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </div>
                    )}
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle>کد هدیه (شارژ کیف پول)</CardTitle>
                    <CardDescription>هر مشتری یک بار می‌تواند هر کد را بزند و مبلغش به کیف پولش اضافه می‌شود.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-end">
                        <Field label="کد (فقط حروف انگلیسی)">
                            <Input dir="ltr" value={g.code} onChange={(e) => setG({ ...g, code: e.target.value.replace(/[^A-Za-z]/g, '') })} placeholder="NOWRUZ" />
                        </Field>
                        <Field label="مبلغ (تومان)">
                            <Input dir="ltr" inputMode="numeric" value={g.price} onChange={(e) => setG({ ...g, price: onlyDigits(e.target.value) })} />
                        </Field>
                        <Button
                            disabled={act.busy || !g.code || !g.price}
                            onClick={async () => {
                                const r = await act.run(() => api.post<BotGiftCode[]>('giftcodes', g))
                                if (r && r !== true) {
                                    gifts.setData(r)
                                    setG({ code: '', price: '' })
                                }
                            }}
                        >
                            <Plus className="h-4 w-4 ml-1" /> ساخت
                        </Button>
                    </div>
                    {!gifts.data?.length ? (
                        <Empty text="کد هدیه‌ای نیست" />
                    ) : (
                        <div className="overflow-x-auto">
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead className="text-right">کد</TableHead>
                                        <TableHead className="text-right">مبلغ</TableHead>
                                        <TableHead className="text-right">دفعات استفاده</TableHead>
                                        <TableHead></TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {gifts.data.map((x) => (
                                        <TableRow key={x.id}>
                                            <TableCell dir="ltr" className="text-right font-mono">{x.code}</TableCell>
                                            <TableCell>{money(x.price)}</TableCell>
                                            <TableCell>{num(x.used)}</TableCell>
                                            <TableCell className="text-left">
                                                <Button
                                                    size="xs"
                                                    variant="ghost"
                                                    onClick={async () => {
                                                        if (!confirm(`کد ${x.code} حذف شود؟`)) return
                                                        if (await act.run(() => api.del(`giftcodes/${x.id}`))) gifts.reload()
                                                    }}
                                                >
                                                    <Trash2 className="h-4 w-4 text-destructive" />
                                                </Button>
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    )
}
