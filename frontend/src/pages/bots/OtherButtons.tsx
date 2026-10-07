import { useMemo, useState } from 'react'
import { Check, Palette, Plus, RotateCcw, Trash2 } from 'lucide-react'
import { BotAPI, BotLabelStyles, LabelStyle } from '@/lib/bots-api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBox, Loading, Notice, Spinner, useAction, useLoad } from './common'
import { PremiumEmoji } from './emoji'
import { COLORS, EmojiPicker, btnClass } from './ButtonsTab'

// Colour and premium icon for every other button of the bot — categories,
// products, locations, payment methods, back buttons… The bot matches them
// by the button's text, wherever that button shows up.

type Group = 'categories' | 'products' | 'locations' | 'fixed' | 'custom'
const GROUPS: Array<{ key: Group; label: string; hint: string }> = [
    { key: 'categories', label: 'دسته‌بندی‌ها', hint: 'دکمه‌های دسته‌بندی محصولات' },
    { key: 'products', label: 'محصولات', hint: 'دکمه‌ی هر محصول در لیست خرید و تمدید' },
    { key: 'locations', label: 'لوکیشن‌ها', hint: 'دکمه‌ی هر سرور/لوکیشن هنگام خرید و اکانت تست' },
    { key: 'fixed', label: 'دکمه‌های ثابت', hint: 'بازگشت، روش‌های پرداخت، تمدید، صفحه‌ی بعد و…' },
    { key: 'custom', label: 'متن دلخواه', hint: 'هر دکمه‌ی دیگری؛ متن آن را دقیقاً همان‌طور که در ربات است بنویسید' },
]

export function OtherButtons({ api, botKey }: { api: BotAPI; botKey: string }) {
    const remote = useLoad(() => api.get<BotLabelStyles>('button-styles'), [api])
    if (remote.loading && !remote.data) return <Loading />
    if (!remote.data) return <ErrorBox error={remote.error} />
    return <Editor key={JSON.stringify(remote.data.styles)} api={api} botKey={botKey} d={remote.data} onSaved={remote.setData} />
}

function Editor({ api, botKey, d, onSaved }: { api: BotAPI; botKey: string; d: BotLabelStyles; onSaved: (v: BotLabelStyles) => void }) {
    const [styles, setStyles] = useState<Record<string, LabelStyle>>(d.styles)
    const [group, setGroup] = useState<Group>(d.suggestions.categories.length ? 'categories' : 'products')
    const [selected, setSelected] = useState<string | null>(null)
    const [extra, setExtra] = useState<string[]>([])
    const [draft, setDraft] = useState('')
    const act = useAction()

    const known = useMemo(() => new Set([...d.suggestions.categories, ...d.suggestions.products, ...d.suggestions.locations, ...d.suggestions.fixed]), [d])
    const labels: Record<Group, string[]> = {
        ...d.suggestions,
        custom: [...new Set([...Object.keys(styles).filter((l) => !known.has(l)), ...extra])],
    }
    const list = labels[group]
    const dirty = JSON.stringify(clean(styles)) !== JSON.stringify(clean(d.styles))
    const count = Object.keys(clean(styles)).length
    const cur = selected ? styles[selected] || {} : {}

    const set = (label: string, patch: LabelStyle) =>
        setStyles((s) => {
            const next = { ...(s[label] || {}), ...patch }
            return { ...s, [label]: next }
        })

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <Palette className="h-5 w-5 text-primary" /> رنگ و آیکون بقیه‌ی دکمه‌ها
                </CardTitle>
                <CardDescription className="leading-6">
                    دسته‌بندی‌ها، محصولات، لوکیشن‌ها، روش‌های پرداخت و هر دکمه‌ی دیگر ربات. هر جا دکمه‌ای با همین متن نمایش داده شود، همین رنگ و آیکون
                    را می‌گیرد. دکمه‌های منوی اصلی از بخش بالا تنظیم می‌شوند.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                <nav className="flex gap-1 overflow-x-auto pb-1">
                    {GROUPS.map((g) => {
                        const n = labels[g.key].filter((l) => isSet(styles[l])).length
                        return (
                            <button
                                key={g.key}
                                onClick={() => {
                                    setGroup(g.key)
                                    setSelected(null)
                                }}
                                className={cn(
                                    'flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition',
                                    group === g.key ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground hover:bg-accent'
                                )}
                            >
                                {g.label}
                                {n > 0 && <span className="rounded-full bg-background/30 px-1.5 text-[11px]">{n.toLocaleString('fa-IR')}</span>}
                            </button>
                        )
                    })}
                </nav>
                <p className="text-xs text-muted-foreground">{GROUPS.find((g) => g.key === group)?.hint}</p>

                {group === 'custom' && (
                    <form
                        className="flex gap-2"
                        onSubmit={(e) => {
                            e.preventDefault()
                            const t = draft.trim()
                            if (!t) return
                            setExtra((x) => (x.includes(t) ? x : [...x, t]))
                            setSelected(t)
                            setDraft('')
                        }}
                    >
                        <Input value={draft} maxLength={200} onChange={(e) => setDraft(e.target.value)} placeholder="متن دکمه، مثلاً: 🔄 تمدید سرویس" />
                        <Button type="submit" variant="outline" disabled={!draft.trim()}>
                            <Plus className="h-4 w-4 ml-1" /> افزودن
                        </Button>
                    </form>
                )}

                <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
                    <div className="space-y-2">
                        {!list.length ? (
                            <p className="rounded-lg bg-muted/40 p-3 text-sm text-muted-foreground">
                                {group === 'custom' ? 'هنوز دکمه‌ای اضافه نشده است.' : 'در این ربات چیزی در این بخش وجود ندارد.'}
                            </p>
                        ) : (
                            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                                {list.map((l) => {
                                    const s = styles[l] || {}
                                    return (
                                        <button
                                            key={l}
                                            onClick={() => setSelected(l)}
                                            className={cn(
                                                'flex min-h-11 items-center justify-center gap-1.5 rounded-xl px-3 py-2 text-sm shadow-sm transition',
                                                btnClass(s.style),
                                                selected === l ? 'ring-2 ring-primary ring-offset-2 ring-offset-background' : 'hover:opacity-90'
                                            )}
                                        >
                                            {s.emoji && <PremiumEmoji api={api} botKey={botKey} id={s.emoji} className="h-5 w-5" />}
                                            <span className="truncate">{l}</span>
                                        </button>
                                    )
                                })}
                            </div>
                        )}
                    </div>

                    <div className="space-y-3">
                        {!selected ? (
                            <p className="rounded-xl border border-dashed border-border p-4 text-center text-sm text-muted-foreground">
                                روی یک دکمه بزنید تا رنگ و آیکونش را انتخاب کنید.
                            </p>
                        ) : (
                            <div className="space-y-3 rounded-xl border border-border p-3">
                                <div className="flex items-center justify-between gap-2">
                                    <b className="truncate text-sm">{selected}</b>
                                    <Button size="sm" variant="ghost" onClick={() => set(selected, { style: '', emoji: '' })}>
                                        <Trash2 className="h-4 w-4 ml-1 text-destructive" /> پاک‌کردن
                                    </Button>
                                </div>
                                <div className="grid grid-cols-4 gap-2">
                                    {COLORS.map((x) => (
                                        <button
                                            key={x.v}
                                            onClick={() => set(selected, { style: x.v })}
                                            className={cn(
                                                'flex flex-col items-center gap-1.5 rounded-xl border p-2 text-xs transition',
                                                (cur.style || '') === x.v ? 'border-primary ring-1 ring-primary' : 'border-border hover:bg-accent/50'
                                            )}
                                        >
                                            <span className={cn('flex h-7 w-7 items-center justify-center rounded-md', x.swatch)}>
                                                {(cur.style || '') === x.v && <Check className={cn('h-4 w-4', x.v ? 'text-white' : 'text-slate-700')} />}
                                            </span>
                                            {x.label}
                                        </button>
                                    ))}
                                </div>
                                <EmojiPicker api={api} botKey={botKey} value={cur.emoji || ''} onChange={(v) => set(selected, { emoji: v })} />
                            </div>
                        )}
                    </div>
                </div>

                <ErrorBox error={act.error} />
                <Notice text={act.notice} />
                <div className="flex flex-wrap items-center gap-2">
                    <Button
                        disabled={!dirty || act.busy}
                        onClick={async () => {
                            const r = await act.run(() => api.put<BotLabelStyles>('button-styles', { styles: clean(styles) }), 'ذخیره شد؛ از پیام بعدی ربات اعمال می‌شود.')
                            if (r && r !== true) onSaved(r)
                        }}
                    >
                        {act.busy && <Spinner className="ml-1" />} ذخیره
                    </Button>
                    {dirty && (
                        <Button variant="outline" onClick={() => setStyles(d.styles)}>
                            <RotateCcw className="h-4 w-4 ml-1" /> برگرداندن
                        </Button>
                    )}
                    <span className="text-xs text-muted-foreground">{count.toLocaleString('fa-IR')} دکمه تنظیم شده</span>
                </div>
            </CardContent>
        </Card>
    )
}

function isSet(s?: LabelStyle) {
    return !!s && (!!s.style || !!s.emoji)
}

function clean(m: Record<string, LabelStyle>): Record<string, LabelStyle> {
    const out: Record<string, LabelStyle> = {}
    for (const k of Object.keys(m).sort()) {
        const s = m[k]
        if (isSet(s)) out[k] = { ...(s.style ? { style: s.style } : {}), ...(s.emoji ? { emoji: s.emoji } : {}) }
    }
    return out
}
