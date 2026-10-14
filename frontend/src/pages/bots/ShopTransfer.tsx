import { useRef, useState } from 'react'
import { Download, Upload } from 'lucide-react'
import { BotAPI, BotCategory, BotDiscount, BotGiftCode, BotPanel, BotProduct } from '@/lib/bots-api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ErrorBox, Notice, Spinner, num, useAction } from './common'

// One shop (categories, products, discount codes, gift codes) moved between
// two bots as a versioned JSON file. Everything is keyed by name/code on
// purpose: ids belong to one bot and mean nothing on another.
const FORMAT = 'mit-seller-shop'
const VERSION = 1
const MAX_FILE_BYTES = 5 * 1024 * 1024
const MAX_ITEMS = 1000

interface ShopProduct {
    name: string
    location: string
    volume: string
    days: string
    price: string
    category: string | null
}
interface ShopDiscount {
    code: string
    percent: string
    limit: string
    first_purchase_only: boolean
}
interface ShopGift {
    code: string
    price: string
}
interface ShopDoc {
    format: string
    version: number
    exported_at: string
    source: { name: string }
    data: {
        categories: Array<{ name: string }>
        products: ShopProduct[]
        discounts: ShopDiscount[]
        giftcodes: ShopGift[]
    }
}

// ---------------------------------------------------------------- reading a file

const str = (v: unknown): string => (v === null || v === undefined ? '' : String(v))

function fail(error: string): { error: string } {
    return { error }
}

function listOf<T>(raw: unknown, one: (x: Record<string, unknown>) => T): T[] | string {
    if (!Array.isArray(raw)) return 'بخشی از فایل خوانده نشد'
    if (raw.length > MAX_ITEMS) return `فایل بیش از ${MAX_ITEMS} ردیف دارد`
    return raw.filter((x) => x && typeof x === 'object').map((x) => one(x as Record<string, unknown>))
}

function parseShopDoc(text: string): { doc?: ShopDoc; error?: string } {
    let raw: unknown
    try {
        raw = JSON.parse(text)
    } catch {
        return fail('این فایل JSON معتبر نیست.')
    }
    if (!raw || typeof raw !== 'object') return fail('ساختار فایل درست نیست.')
    const o = raw as Record<string, unknown>
    if (o.format !== FORMAT) return fail('این فایل خروجی فروشگاه ربات نیست.')
    if (o.version !== VERSION) return fail(`نسخه‌ی فایل (${str(o.version)}) پشتیبانی نمی‌شود.`)
    const d = o.data
    if (!d || typeof d !== 'object') return fail('بخش data در فایل نیست.')
    const data = d as Record<string, unknown>

    const categories = listOf(data.categories, (x) => ({ name: str(x.name).trim() }))
    if (typeof categories === 'string') return fail(categories)
    const products = listOf(data.products, (x) => ({
        name: str(x.name).trim(),
        location: str(x.location).trim() || '/all',
        volume: str(x.volume),
        days: str(x.days),
        price: str(x.price),
        category: str(x.category).trim() || null,
    }))
    if (typeof products === 'string') return fail(products)
    const discounts = listOf(data.discounts, (x) => ({
        code: str(x.code).trim(),
        percent: str(x.percent),
        limit: str(x.limit),
        first_purchase_only: x.first_purchase_only === true || x.first_purchase_only === 'true' || x.first_purchase_only === 1,
    }))
    if (typeof discounts === 'string') return fail(discounts)
    const giftcodes = listOf(data.giftcodes, (x) => ({ code: str(x.code).trim(), price: str(x.price) }))
    if (typeof giftcodes === 'string') return fail(giftcodes)

    const noName = [...categories.map((c) => c.name), ...products.map((p) => p.name)].some((n) => !n)
    const noCode = [...discounts.map((x) => x.code), ...giftcodes.map((x) => x.code)].some((n) => !n)
    if (noName || noCode) return fail('ردیفی در فایل نام یا کد ندارد.')

    return {
        doc: {
            format: FORMAT,
            version: VERSION,
            exported_at: str(o.exported_at),
            source: { name: str((o.source as Record<string, unknown> | undefined)?.name) || 'نامشخص' },
            data: {
                categories: categories.filter((c) => c.name),
                products,
                discounts,
                giftcodes,
            },
        },
    }
}

// ---------------------------------------------------------------- planning

interface CategoryChange {
    create: string[]
    remove: Array<{ id: string; name: string }>
}
interface ProductChange {
    create: ShopProduct[]
    update: Array<{ id: string; item: ShopProduct }>
    remove: Array<{ id: string; name: string }>
}
interface DiscountChange {
    create: ShopDiscount[]
    replace: Array<{ id: string; item: ShopDiscount }>
    remove: Array<{ id: string; code: string }>
}
interface GiftChange {
    create: ShopGift[]
    replace: Array<{ id: string; item: ShopGift }>
    remove: Array<{ id: string; code: string }>
}
interface Plan {
    sourceName: string
    categories: CategoryChange
    products: ProductChange
    discounts: DiscountChange
    giftcodes: GiftChange
    notes: string[]
}

const same = (a: string, b: string) => String(a ?? '') === String(b ?? '')

function buildPlan(
    doc: ShopDoc,
    live: { categories: BotCategory[]; products: BotProduct[]; discounts: BotDiscount[]; giftcodes: BotGiftCode[]; panels: BotPanel[] }
): Plan {
    const notes: string[] = []
    const fileCats = doc.data.categories.map((c) => c.name)
    const liveCatId = new Map(live.categories.map((c) => [c.remark, c.id]))
    const categories: CategoryChange = {
        create: fileCats.filter((n) => !liveCatId.has(n)),
        remove: live.categories.filter((c) => !fileCats.includes(c.remark)).map((c) => ({ id: c.id, name: c.remark })),
    }

    const panelNames = new Set(live.panels.map((p) => p.name_panel))
    const fileProducts = doc.data.products
    const liveProductByName = new Map(live.products.map((p) => [p.name_product, p]))
    // A product names the server it sells from; if the target bot does not have
    // that server it can only fall back to "all servers".
    const mapLocation = (loc: string): string => {
        if (loc === '/all') return '/all'
        if (!panelNames.has(loc)) {
            if (!notes.some((n) => n.includes(loc))) notes.push(`سرور «${loc}» روی ربات مقصد نیست؛ این محصول روی «همه سرورها» می‌آید.`)
            return '/all'
        }
        return loc
    }
    const target = (p: ShopProduct) => ({
        name: p.name,
        location: mapLocation(p.location),
        volume: p.volume,
        days: p.days,
        price: p.price,
        category: p.category,
    })
    const products: ProductChange = { create: [], update: [], remove: [] }
    const fileNames = new Set<string>()
    for (const p of fileProducts) {
        const want = target(p)
        fileNames.add(want.name)
        const have = liveProductByName.get(want.name)
        if (!have) {
            products.create.push(want)
            continue
        }
        const catId = want.category ? liveCatId.get(want.category) ?? '' : ''
        const differs =
            !same(have.Location, want.location) ||
            !same(have.Volume_constraint, want.volume) ||
            !same(have.Service_time, want.days) ||
            !same(have.price_product, want.price) ||
            !same(have.Category || '', catId)
        if (differs) products.update.push({ id: have.id, item: want })
    }
    products.remove = live.products.filter((p) => !fileNames.has(p.name_product)).map((p) => ({ id: p.id, name: p.name_product }))

    // The bot has no "edit code" call, so a code whose values differ is
    // deleted and made again - which resets how many times it was used.
    const fileDiscounts = doc.data.discounts
    const liveDiscountByCode = new Map(live.discounts.map((x) => [x.codeDiscount, x]))
    const discounts: DiscountChange = { create: [], replace: [], remove: [] }
    const discCodes = new Set<string>()
    for (const x of fileDiscounts) {
        discCodes.add(x.code)
        const have = liveDiscountByCode.get(x.code)
        if (!have) {
            discounts.create.push(x)
            continue
        }
        const differs = !same(have.price, x.percent) || !same(have.limitDiscount, x.limit) || (have.usefirst === '1') !== x.first_purchase_only
        if (differs) discounts.replace.push({ id: have.id, item: x })
    }
    discounts.remove = live.discounts.filter((x) => !discCodes.has(x.codeDiscount)).map((x) => ({ id: x.id, code: x.codeDiscount }))
    if (discounts.replace.length) notes.push('کد تخفیفی که روی مقصد تغییر کرده دوباره ساخته می‌شود و شمارنده‌ی استفاده‌اش صفر می‌شود.')

    const fileGifts = doc.data.giftcodes
    const liveGiftByCode = new Map(live.giftcodes.map((x) => [x.code, x]))
    const giftcodes: GiftChange = { create: [], replace: [], remove: [] }
    const giftCodes = new Set<string>()
    for (const x of fileGifts) {
        giftCodes.add(x.code)
        const have = liveGiftByCode.get(x.code)
        if (!have) {
            giftcodes.create.push(x)
            continue
        }
        if (!same(have.price, x.price)) giftcodes.replace.push({ id: have.id, item: x })
    }
    giftcodes.remove = live.giftcodes.filter((x) => !giftCodes.has(x.code)).map((x) => ({ id: x.id, code: x.code }))
    if (giftcodes.replace.length) notes.push('کد هدیه‌ای که مبلغش فرق دارد دوباره ساخته می‌شود و شمارنده‌اش صفر می‌شود.')
    notes.push('برای اینکه دسته‌ها به مشتری نشان داده شوند، «دسته‌بندی محصولات» در تنظیمات ربات مقصد باید روشن باشد.')

    return { sourceName: doc.source.name, categories, products, discounts, giftcodes, notes }
}

const planTotal = (p: Plan): number =>
    p.categories.create.length +
    p.categories.remove.length +
    p.products.create.length +
    p.products.update.length +
    p.products.remove.length +
    p.discounts.create.length +
    p.discounts.replace.length * 2 +
    p.discounts.remove.length +
    p.giftcodes.create.length +
    p.giftcodes.replace.length * 2 +
    p.giftcodes.remove.length

const planEmpty = (p: Plan): boolean => planTotal(p) === 0

// ---------------------------------------------------------------- the card

export function ShopTransfer({ api, botName }: { api: BotAPI; botName: string }) {
    const fileRef = useRef<HTMLInputElement>(null)
    const act = useAction()
    const [plan, setPlan] = useState<Plan | null>(null)
    const [busy, setBusy] = useState(false)
    const [step, setStep] = useState('')
    const [result, setResult] = useState<{ done: number; failed: string[] } | null>(null)

    const exportShop = () =>
        act.run(async () => {
            const [categories, products, discounts, giftcodes] = await Promise.all([
                api.get<BotCategory[]>('categories'),
                api.get<BotProduct[]>('products'),
                api.get<BotDiscount[]>('discounts'),
                api.get<BotGiftCode[]>('giftcodes'),
            ])
            const catName = (id: string | null) => categories.find((c) => c.id === id)?.remark || null
            const doc: ShopDoc = {
                format: FORMAT,
                version: VERSION,
                exported_at: new Date().toISOString(),
                source: { name: botName },
                data: {
                    categories: categories.map((c) => ({ name: c.remark })),
                    products: products.map((p) => ({
                        name: p.name_product,
                        location: p.Location,
                        volume: p.Volume_constraint,
                        days: p.Service_time,
                        price: p.price_product,
                        category: catName(p.Category),
                    })),
                    discounts: discounts.map((x) => ({
                        code: x.codeDiscount,
                        percent: x.price,
                        limit: x.limitDiscount,
                        first_purchase_only: x.usefirst === '1',
                    })),
                    giftcodes: giftcodes.map((x) => ({ code: x.code, price: x.price })),
                },
            }
            const blob = new Blob([JSON.stringify(doc, null, 2)], { type: 'application/json' })
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            const day = new Date().toISOString().slice(0, 10).replace(/-/g, '')
            a.href = url
            a.download = `shop-${(botName || 'bot').replace(/[^\w.@-]+/g, '_')}-${day}.json`
            document.body.appendChild(a)
            a.click()
            a.remove()
            setTimeout(() => URL.revokeObjectURL(url), 10_000)
        }, 'فایل خروجی ساخته شد')

    const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        e.target.value = ''
        if (!file) return
        if (file.size > MAX_FILE_BYTES) {
            act.setError('فایل بزرگ‌تر از ۵ مگابایت است')
            return
        }
        setResult(null)
        void act.run(async () => {
            const { doc, error } = parseShopDoc(await file.text())
            if (!doc) throw new Error(error)
            const [categories, products, discounts, giftcodes, panels] = await Promise.all([
                api.get<BotCategory[]>('categories'),
                api.get<BotProduct[]>('products'),
                api.get<BotDiscount[]>('discounts'),
                api.get<BotGiftCode[]>('giftcodes'),
                api.get<BotPanel[]>('panels'),
            ])
            setPlan(buildPlan(doc, { categories, products, discounts, giftcodes, panels }))
        })
    }

    const apply = async (p: Plan) => {
        setBusy(true)
        setStep('')
        const failed: string[] = []
        let done = 0
        const total = planTotal(p)
        const tick = async (label: string, fn: () => Promise<unknown>) => {
            done += 1
            setStep(`${num(done)} از ${num(total)} — ${label}`)
            try {
                await fn()
            } catch (err) {
                failed.push(`${label}: ${err instanceof Error ? err.message : 'خطا'}`)
            }
        }

        // Create first, delete last: a run that dies halfway leaves the
        // target with a superset of the file, and running it again converges.
        for (const name of p.categories.create) await tick(`ساخت دسته «${name}»`, () => api.post('categories', { name }))
        let idByName = new Map<string, string>()
        try {
            const cats = await api.get<BotCategory[]>('categories')
            idByName = new Map(cats.map((c) => [c.remark, c.id]))
        } catch (err) {
            failed.push(`خواندن دسته‌ها: ${err instanceof Error ? err.message : 'خطا'}`)
        }
        const body = (item: ShopProduct) => ({
            name: item.name,
            location: item.location,
            volume: item.volume,
            days: item.days,
            price: item.price,
            category_id: (item.category && idByName.get(item.category)) || '',
        })
        for (const item of p.products.create) await tick(`ساخت محصول «${item.name}»`, () => api.post('products', body(item)))
        for (const u of p.products.update) await tick(`ویرایش محصول «${u.item.name}»`, () => api.put(`products/${u.id}`, body(u.item)))
        for (const x of p.discounts.create) await tick(`ساخت کد تخفیف «${x.code}»`, () =>
            api.post('discounts', { code: x.code, percent: x.percent, limit: x.limit, first_purchase_only: x.first_purchase_only })
        )
        for (const r of p.discounts.replace) {
            await tick(`حذف کد تخفیف «${r.item.code}»`, () => api.del(`discounts/${r.id}`))
            await tick(`ساخت دوباره‌ی کد «${r.item.code}»`, () =>
                api.post('discounts', {
                    code: r.item.code,
                    percent: r.item.percent,
                    limit: r.item.limit,
                    first_purchase_only: r.item.first_purchase_only,
                })
            )
        }
        for (const x of p.giftcodes.create) await tick(`ساخت کد هدیه «${x.code}»`, () => api.post('giftcodes', { code: x.code, price: x.price }))
        for (const r of p.giftcodes.replace) {
            await tick(`حذف کد هدیه «${r.item.code}»`, () => api.del(`giftcodes/${r.id}`))
            await tick(`ساخت دوباره‌ی کد «${r.item.code}»`, () => api.post('giftcodes', { code: r.item.code, price: r.item.price }))
        }
        for (const r of p.products.remove) await tick(`حذف محصول «${r.name}»`, () => api.del(`products/${r.id}`))
        for (const r of p.discounts.remove) await tick(`حذف کد تخفیف «${r.code}»`, () => api.del(`discounts/${r.id}`))
        for (const r of p.giftcodes.remove) await tick(`حذف کد هدیه «${r.code}»`, () => api.del(`giftcodes/${r.id}`))
        for (const r of p.categories.remove) await tick(`حذف دسته «${r.name}»`, () => api.del(`categories/${r.id}`))

        setBusy(false)
        setStep('')
        setResult({ done, failed })
    }

    return (
        <>
            <Card>
                <CardHeader>
                    <CardTitle>انتقال فروشگاه (JSON)</CardTitle>
                    <CardDescription>
                        دسته‌ها، محصولات، کد تخفیف و کد هدیه‌ی همین ربات را خروجی بگیرید و روی ربات دیگری وارد کنید: اول ربات مقصد را از بالای صفحه
                        انتخاب کنید، بعد «ورود از فایل» را بزنید. مقصد دقیقاً مثل فایل می‌شود؛ هرچه در مقصد است و در فایل نیست حذف می‌شود.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                    <ErrorBox error={act.error} />
                    <Notice text={act.notice} />
                    <div className="flex flex-wrap gap-2">
                        <Button variant="outline" disabled={act.busy || busy} onClick={exportShop}>
                            {act.busy ? <Spinner className="ml-2" /> : <Download className="h-4 w-4 ml-1" />} خروجی JSON
                        </Button>
                        <Button variant="outline" disabled={act.busy || busy} onClick={() => fileRef.current?.click()}>
                            <Upload className="h-4 w-4 ml-1" /> ورود از فایل
                        </Button>
                        <input ref={fileRef} type="file" accept="application/json,.json" className="hidden" onChange={onFile} />
                    </div>
                    {busy && <p className="text-sm text-muted-foreground">{step || 'در حال اجرا…'}</p>}
                </CardContent>
            </Card>

            <Dialog
                open={!!plan}
                onOpenChange={(o) => {
                    if (!o && !busy) setPlan(null)
                }}
            >
                <DialogContent dir="rtl" className="max-w-2xl">
                    <DialogHeader className="pr-8 text-right">
                        <DialogTitle>ورود فروشگاه از «{plan?.sourceName}» به «{botName}»</DialogTitle>
                    </DialogHeader>
                    {plan && (
                        <div className="space-y-3 text-sm">
                            {result ? (
                                <>
                                    <p>
                                        {result.failed.length ? (
                                            <span className="text-destructive">
                                                {num(result.done)} کار انجام شد و {num(result.failed.length)} مورد خطا داد.
                                            </span>
                                        ) : (
                                            <span className="text-brand-green">فروشگاه مقصد با فایل هماهنگ شد.</span>
                                        )}
                                    </p>
                                    <ErrorBox error={result.failed.join('، ') || null} />
                                    <p className="text-xs text-muted-foreground">
                                        لیست محصولات و کدها با رفتن به سربرگ‌های «محصولات» و «تخفیف و هدیه» تازه می‌شود.
                                    </p>
                                    <div className="flex justify-end gap-2 pt-2">
                                        <Button
                                            onClick={() => {
                                                setPlan(null)
                                                setResult(null)
                                            }}
                                        >
                                            بستن
                                        </Button>
                                    </div>
                                </>
                            ) : (
                                <>
                                    <p className="text-muted-foreground">مقصد با فایل یکی می‌شود؛ مواردی که در فایل نیستند حذف خواهند شد:</p>
                                    <div className="space-y-2">
                                        <Row
                                            label="دسته‌بندی"
                                            add={plan.categories.create}
                                            del={plan.categories.remove.map((x) => x.name)}
                                        />
                                        <Row
                                            label="محصول"
                                            add={plan.products.create.map((x) => x.name)}
                                            upd={plan.products.update.map((x) => x.item.name)}
                                            del={plan.products.remove.map((x) => x.name)}
                                        />
                                        <Row
                                            label="کد تخفیف"
                                            add={plan.discounts.create.map((x) => x.code)}
                                            upd={plan.discounts.replace.map((x) => x.item.code)}
                                            del={plan.discounts.remove.map((x) => x.code)}
                                        />
                                        <Row
                                            label="کد هدیه"
                                            add={plan.giftcodes.create.map((x) => x.code)}
                                            upd={plan.giftcodes.replace.map((x) => x.item.code)}
                                            del={plan.giftcodes.remove.map((x) => x.code)}
                                        />
                                    </div>
                                    {plan.notes.map((n) => (
                                        <p key={n} className="text-xs text-muted-foreground leading-5">
                                            {n}
                                        </p>
                                    ))}
                                    {planEmpty(plan) && <p className="text-muted-foreground">فایل همین حالا با ربات مقصد یکی است؛ کاری انجام نمی‌شود.</p>}
                                    <div className="flex justify-end gap-2 pt-2">
                                        <Button variant="outline" disabled={busy} onClick={() => setPlan(null)}>
                                            انصراف
                                        </Button>
                                        <Button variant="destructive" disabled={busy || planEmpty(plan)} onClick={() => apply(plan)}>
                                            {busy && <Spinner className="ml-2" />} اعمال تغییرات
                                        </Button>
                                    </div>
                                </>
                            )}
                        </div>
                    )}
                </DialogContent>
            </Dialog>
        </>
    )
}

function Row({ label, add, upd, del }: { label: string; add: string[]; upd?: string[]; del: string[] }) {
    const names = (xs: string[]) => (xs.length <= 6 ? xs.join('، ') : `${xs.slice(0, 6).join('، ')} و ${num(xs.length - 6)} مورد دیگر`)
    return (
        <div className="rounded-lg border border-border p-3 space-y-1">
            <div className="font-medium">{label}</div>
            <div className="text-xs text-muted-foreground leading-5">
                {add.length > 0 && <div>ساخته می‌شود ({num(add.length)}): {names(add)}</div>}
                {upd && upd.length > 0 && <div>ویرایش می‌شود ({num(upd.length)}): {names(upd)}</div>}
                {del.length > 0 && <div className="text-destructive">حذف می‌شود ({num(del.length)}): {names(del)}</div>}
                {add.length === 0 && (!upd || upd.length === 0) && del.length === 0 && <div>بدون تغییر</div>}
            </div>
        </div>
    )
}
