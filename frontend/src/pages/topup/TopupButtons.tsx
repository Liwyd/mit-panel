import { useMemo, useRef, useState } from 'react'
import { Search } from 'lucide-react'
import { BotAPI, TopupButtons as Buttons } from '@/lib/bots-api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBox, Field, Loading, Notice, Spinner, useAction, useLoad } from '../bots/common'
import { COLORS, EmojiPicker, btnClass } from '../bots/ButtonsTab'
import { PremiumEmoji } from '../bots/emoji'

type Style = { style: string; emoji: string }

// Each of the bot's buttons: colour, premium icon and label. Where a button
// sits is the bot's own business (it depends on who is looking), so only how
// it looks is edited here.
export function TopupButtons({ api }: { api: BotAPI }) {
    const remote = useLoad(() => api.get<Buttons>('buttons'), [api])
    if (remote.loading && !remote.data) return <Loading />
    if (!remote.data) return <ErrorBox error={remote.error} />
    return <Editor api={api} d={remote.data} onSaved={remote.setData} />
}

function Editor({ api, d, onSaved }: { api: BotAPI; d: Buttons; onSaved: (b: Buttons) => void }) {
    const [styles, setStyles] = useState<Record<string, Style>>({})
    const [labels, setLabels] = useState<Record<string, string>>({})
    const [selected, setSelected] = useState<string | null>(null)
    const [query, setQuery] = useState('')
    const act = useAction()
    const botKey = String(api.id)
    // on a phone the editor sits above the list, out of sight of the tap
    const editorRef = useRef<HTMLDivElement>(null)
    const choose = (k: string) => {
        setSelected(k)
        if (window.innerWidth < 1024) setTimeout(() => editorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
    }

    const st = (k: string): Style => styles[k] ?? d.buttons[k] ?? { style: '', emoji: '' }
    const label = (k: string) => labels[k] ?? d.labels[k] ?? k
    const setSt = (k: string, v: Partial<Style>) => setStyles((s) => ({ ...s, [k]: { ...st(k), ...v } }))

    const keys = useMemo(() => {
        const q = query.trim().toLowerCase()
        return Object.keys(d.buttons).filter((k) => !q || k.toLowerCase().includes(q) || (d.labels[k] || '').toLowerCase().includes(q))
    }, [d, query])

    const styleChanges = Object.keys(styles).filter((k) => {
        const a = styles[k]
        const b = d.buttons[k] || { style: '', emoji: '' }
        return a.style !== b.style || a.emoji !== b.emoji
    })
    const labelChanges = Object.keys(labels).filter((k) => labels[k].trim() && labels[k] !== d.labels[k])
    const changes = new Set([...styleChanges, ...labelChanges]).size

    const save = async () => {
        const res = await act.run(async () => {
            if (labelChanges.length) await api.put('texts', Object.fromEntries(labelChanges.map((k) => [k, labels[k]])))
            return api.put<Buttons>('buttons', { buttons: Object.fromEntries(styleChanges.map((k) => [k, styles[k]])) })
        }, 'ذخیره شد؛ کاربران با منوی بعدی دکمه‌های تازه را می‌بینند')
        if (res && res !== true) {
            onSaved(res as Buttons)
            setStyles({})
            setLabels({})
        }
    }

    const sel = selected && d.buttons[selected] ? selected : null

    return (
        <Card>
            <CardHeader>
                <CardTitle>دکمه‌های ربات</CardTitle>
                <CardDescription className="leading-6">
                    روی یک دکمه بزنید تا رنگ (آبی، سبز، قرمز)، آیکون ایموجی پریمیوم و برچسبش را عوض کنید. رنگ دکمه در نسخه‌های قدیمی تلگرام دیده نمی‌شود و آیکون
                    پریمیوم فقط وقتی نمایش داده می‌شود که سازنده‌ی ربات تلگرام پریمیوم داشته باشد.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
                    <div className="min-w-0 space-y-3">
                        <div className="relative">
                            <Search className="absolute right-3 top-3 h-4 w-4 text-muted-foreground" />
                            <Input className="pr-9" placeholder="جستجوی دکمه…" value={query} onChange={(e) => setQuery(e.target.value)} />
                        </div>
                        <div className="grid gap-2 sm:grid-cols-2">
                            {keys.map((k) => {
                                const s = st(k)
                                return (
                                    <button
                                        key={k}
                                        onClick={() => choose(k)}
                                        className={cn(
                                            'flex items-center justify-center gap-1.5 rounded-lg px-3 py-2.5 text-sm shadow-sm transition',
                                            btnClass(s.style),
                                            sel === k ? 'ring-2 ring-primary ring-offset-2 ring-offset-background' : 'hover:opacity-90'
                                        )}
                                    >
                                        {s.emoji && <PremiumEmoji api={api} botKey={botKey} id={s.emoji} className="h-5 w-5" />}
                                        <span className="truncate">{label(k)}</span>
                                    </button>
                                )
                            })}
                        </div>
                    </div>
                    <aside className="order-first lg:order-none">
                        <div ref={editorRef} className="space-y-3 lg:sticky lg:top-4 scroll-mt-4">
                            {!sel ? (
                                <p className="rounded-xl border border-dashed border-border p-4 text-sm text-muted-foreground">یک دکمه را انتخاب کنید.</p>
                            ) : (
                                <>
                                    <code dir="ltr" className="block text-xs text-muted-foreground">
                                        {sel}
                                    </code>
                                    <Field label="برچسب">
                                        <Input value={label(sel)} onChange={(e) => setLabels((l) => ({ ...l, [sel]: e.target.value }))} />
                                    </Field>
                                    <Field label="رنگ" hint={d.defaults[sel] ? `رنگ پیش‌فرض این دکمه: ${COLORS.find((c) => c.v === d.defaults[sel])?.label}` : undefined}>
                                        <div className="flex gap-2">
                                            {COLORS.map((c) => (
                                                <button
                                                    key={c.v}
                                                    title={c.label}
                                                    onClick={() => setSt(sel, { style: c.v })}
                                                    className={cn(
                                                        'flex flex-1 flex-col items-center gap-1 rounded-lg border p-2 text-xs',
                                                        st(sel).style === c.v ? 'border-primary ring-1 ring-primary' : 'border-border'
                                                    )}
                                                >
                                                    <span className={cn('h-5 w-5 rounded-full border border-border', c.swatch)} />
                                                    {c.label}
                                                </button>
                                            ))}
                                        </div>
                                    </Field>
                                    <EmojiPicker api={api} botKey={botKey} value={st(sel).emoji} onChange={(v) => setSt(sel, { emoji: v })} />
                                </>
                            )}
                        </div>
                    </aside>
                </div>
                <ErrorBox error={act.error} />
                <Notice text={act.notice} />
                <div className="sticky bottom-2 flex gap-2 rounded-xl bg-card/90 backdrop-blur p-2 border border-border">
                    <Button disabled={act.busy || !changes} onClick={save}>
                        {act.busy && <Spinner className="ml-2" />} ذخیره {changes ? `(${changes})` : ''}
                    </Button>
                    <Button
                        variant="outline"
                        disabled={!changes}
                        onClick={() => {
                            setStyles({})
                            setLabels({})
                        }}
                    >
                        برگرداندن
                    </Button>
                </div>
            </CardContent>
        </Card>
    )
}
