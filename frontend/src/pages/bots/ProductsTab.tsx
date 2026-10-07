import { useState } from 'react'
import { Plus, Edit2, Trash2, FolderPlus } from 'lucide-react'
import { BotAPI, BotCategory, BotPanel, BotProduct } from '@/lib/bots-api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Empty, ErrorBox, Field, Loading, Spinner, money, selectClass, useAction, useLoad } from './common'

interface ProductForm {
    name: string
    location: string
    volume: string
    days: string
    price: string
    category_id: string
}

export function ProductsTab({ api }: { api: BotAPI }) {
    const products = useLoad(() => api.get<BotProduct[]>('products'), [api])
    const categories = useLoad(() => api.get<BotCategory[]>('categories'), [api])
    const panels = useLoad(() => api.get<BotPanel[]>('panels'), [api])
    const [editing, setEditing] = useState<BotProduct | null>(null)
    const [open, setOpen] = useState(false)
    const [newCat, setNewCat] = useState('')
    const act = useAction()

    const catName = (id: string | null) => categories.data?.find((c) => c.id === id)?.remark || '—'

    if (products.loading && !products.data) return <Loading />

    return (
        <div className="space-y-4">
            <ErrorBox error={products.error || act.error} />
            <Card>
                <CardHeader className="flex flex-row items-center justify-between gap-3">
                    <div>
                        <CardTitle>محصولات</CardTitle>
                        <CardDescription>تعرفه‌هایی که مشتری در ربات می‌خرد. مثل منوی ادمین ربات، تغییر نام، قیمت، حجم یا مدت روی سرویس‌های فروخته‌شده‌ی همین محصول هم ثبت می‌شود (و تمدیدشان با مقدار جدید است).</CardDescription>
                    </div>
                    <Button
                        size="sm"
                        onClick={() => {
                            setEditing(null)
                            setOpen(true)
                        }}
                    >
                        <Plus className="h-4 w-4 ml-1" /> محصول جدید
                    </Button>
                </CardHeader>
                <CardContent>
                    {!products.data?.length ? (
                        <Empty text="محصولی تعریف نشده" />
                    ) : (
                        <div className="overflow-x-auto">
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead className="text-right">نام</TableHead>
                                        <TableHead className="text-right">سرور</TableHead>
                                        <TableHead className="text-right">حجم</TableHead>
                                        <TableHead className="text-right">مدت</TableHead>
                                        <TableHead className="text-right">قیمت</TableHead>
                                        <TableHead className="text-right">دسته</TableHead>
                                        <TableHead></TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {products.data.map((p) => (
                                        <TableRow key={p.id}>
                                            <TableCell className="font-medium">{p.name_product}</TableCell>
                                            <TableCell>{p.Location === '/all' ? 'همه سرورها' : p.Location}</TableCell>
                                            <TableCell>{p.Volume_constraint} گیگ</TableCell>
                                            <TableCell>{p.Service_time} روز</TableCell>
                                            <TableCell>{money(p.price_product)}</TableCell>
                                            <TableCell>{catName(p.Category)}</TableCell>
                                            <TableCell className="whitespace-nowrap text-left">
                                                <Button
                                                    size="xs"
                                                    variant="ghost"
                                                    onClick={() => {
                                                        setEditing(p)
                                                        setOpen(true)
                                                    }}
                                                >
                                                    <Edit2 className="h-4 w-4" />
                                                </Button>
                                                <Button
                                                    size="xs"
                                                    variant="ghost"
                                                    disabled={act.busy}
                                                    onClick={async () => {
                                                        if (!confirm(`«${p.name_product}» حذف شود؟`)) return
                                                        if (await act.run(() => api.del(`products/${p.id}`))) products.reload()
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
                    <CardTitle>دسته‌بندی‌ها</CardTitle>
                    <CardDescription>وقتی «نمایش دسته‌بندی» در تنظیمات روشن باشد، مشتری اول دسته را انتخاب می‌کند.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                    <div className="flex gap-2">
                        <Input value={newCat} onChange={(e) => setNewCat(e.target.value)} placeholder="نام دسته جدید" />
                        <Button
                            disabled={!newCat.trim() || act.busy}
                            onClick={async () => {
                                if (await act.run(() => api.post('categories', { name: newCat.trim() }))) {
                                    setNewCat('')
                                    categories.reload()
                                }
                            }}
                        >
                            <FolderPlus className="h-4 w-4 ml-1" /> افزودن
                        </Button>
                    </div>
                    <div className="flex flex-wrap gap-2">
                        {categories.data?.map((c) => (
                            <span key={c.id} className="inline-flex items-center gap-1 rounded-full border border-border px-3 py-1 text-sm">
                                <button
                                    className="hover:underline"
                                    onClick={async () => {
                                        const name = prompt('نام جدید دسته', c.remark)
                                        if (name && name.trim() && (await act.run(() => api.put(`categories/${c.id}`, { name: name.trim() })))) categories.reload()
                                    }}
                                >
                                    {c.remark}
                                </button>
                                <button
                                    aria-label="حذف"
                                    onClick={async () => {
                                        if (!confirm(`دسته «${c.remark}» حذف شود؟ محصولاتش بدون دسته می‌مانند.`)) return
                                        if (await act.run(() => api.del(`categories/${c.id}`))) {
                                            categories.reload()
                                            products.reload()
                                        }
                                    }}
                                >
                                    <Trash2 className="h-3.5 w-3.5 text-destructive" />
                                </button>
                            </span>
                        ))}
                        {!categories.data?.length && <span className="text-sm text-muted-foreground">دسته‌ای نیست</span>}
                    </div>
                </CardContent>
            </Card>

            <ProductDialog
                open={open}
                product={editing}
                panels={panels.data || []}
                categories={categories.data || []}
                api={api}
                onClose={() => setOpen(false)}
                onSaved={() => {
                    setOpen(false)
                    products.reload()
                }}
            />
        </div>
    )
}

function ProductDialog({
    open,
    product,
    panels,
    categories,
    api,
    onClose,
    onSaved,
}: {
    open: boolean
    product: BotProduct | null
    panels: BotPanel[]
    categories: BotCategory[]
    api: BotAPI
    onClose: () => void
    onSaved: () => void
}) {
    const initial = (): ProductForm =>
        product
            ? {
                  name: product.name_product,
                  location: product.Location,
                  volume: product.Volume_constraint,
                  days: product.Service_time,
                  price: product.price_product,
                  category_id: product.Category || '',
              }
            : { name: '', location: panels[0]?.name_panel || '/all', volume: '', days: '30', price: '', category_id: '' }
    const [form, setForm] = useState<ProductForm>(initial)
    const [key, setKey] = useState<string>('')
    const act = useAction()
    const k = `${open}-${product?.id ?? 'new'}`
    if (k !== key) {
        setKey(k)
        setForm(initial())
        act.setError(null)
    }
    const set = (f: keyof ProductForm, v: string) => setForm((x) => ({ ...x, [f]: v }))
    const digits = (v: string) => v.replace(/[۰-۹]/g, (d) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d))).replace(/[^\d]/g, '')

    const save = async () => {
        const ok = await act.run(() =>
            product ? api.put(`products/${product.id}`, form) : api.post('products', form)
        )
        if (ok) onSaved()
    }

    return (
        <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
            <DialogContent dir="rtl">
                <DialogHeader className="pr-8 text-right">
                    <DialogTitle>{product ? 'ویرایش محصول' : 'محصول جدید'}</DialogTitle>
                </DialogHeader>
                <div className="space-y-3">
                    <Field label="نام محصول">
                        <Input value={form.name} onChange={(e) => set('name', e.target.value)} placeholder="۳۰ گیگ یک ماهه" />
                    </Field>
                    <Field label="سرور">
                        <select className={selectClass} value={form.location} onChange={(e) => set('location', e.target.value)}>
                            <option value="/all">همه سرورها</option>
                            {panels.map((p) => (
                                <option key={p.id} value={p.name_panel}>
                                    {p.name_panel}
                                </option>
                            ))}
                        </select>
                    </Field>
                    <div className="grid grid-cols-3 gap-3">
                        <Field label="حجم (گیگ)">
                            <Input inputMode="numeric" dir="ltr" value={form.volume} onChange={(e) => set('volume', digits(e.target.value))} />
                        </Field>
                        <Field label="مدت (روز)">
                            <Input inputMode="numeric" dir="ltr" value={form.days} onChange={(e) => set('days', digits(e.target.value))} />
                        </Field>
                        <Field label="قیمت (تومان)">
                            <Input inputMode="numeric" dir="ltr" value={form.price} onChange={(e) => set('price', digits(e.target.value))} />
                        </Field>
                    </div>
                    <Field label="دسته">
                        <select className={selectClass} value={form.category_id} onChange={(e) => set('category_id', e.target.value)}>
                            <option value="">بدون دسته</option>
                            {categories.map((c) => (
                                <option key={c.id} value={c.id}>
                                    {c.remark}
                                </option>
                            ))}
                        </select>
                    </Field>
                    <ErrorBox error={act.error} />
                    <div className="flex justify-end gap-2 pt-2">
                        <Button variant="outline" onClick={onClose}>
                            انصراف
                        </Button>
                        <Button onClick={save} disabled={act.busy || !form.name || !form.volume || !form.days || !form.price}>
                            {act.busy && <Spinner className="ml-2" />} ذخیره
                        </Button>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    )
}
