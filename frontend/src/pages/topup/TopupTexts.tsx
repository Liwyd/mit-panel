import { useMemo, useState } from 'react'
import { RotateCcw, Search } from 'lucide-react'
import { BotAPI, TopupText } from '@/lib/bots-api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBox, Loading, Notice, Spinner, useAction, useLoad } from '../bots/common'
import { EmojiBoard, EmojiTextarea } from '../bots/EmojiTextarea'

const FILTERS = [
    { key: 'all', label: 'همه' },
    { key: 'messages', label: 'پیام‌ها' },
    { key: 'buttons', label: 'برچسب دکمه‌ها' },
    { key: 'changed', label: 'تغییرداده‌شده' },
] as const
type Filter = (typeof FILTERS)[number]['key']
const PAGE = 30

// Every text the top-up bot sends, by its name in the bot's texts.py. There
// are hundreds, so the list is searched and paged rather than shown at once.
export function TopupTexts({ api }: { api: BotAPI }) {
    const remote = useLoad(() => api.get<TopupText[]>('texts'), [api])
    const [edits, setEdits] = useState<Record<string, string>>({})
    const [query, setQuery] = useState('')
    const [filter, setFilter] = useState<Filter>('all')
    const [shown, setShown] = useState(PAGE)
    const act = useAction()

    const value = (t: TopupText) => edits[t.id] ?? t.text
    const list = useMemo(() => {
        const q = query.trim().toLowerCase()
        return (remote.data || []).filter((t) => {
            if (filter === 'messages' && t.button) return false
            if (filter === 'buttons' && !t.button) return false
            if (filter === 'changed' && !t.changed && !(t.id in edits)) return false
            return !q || t.id.toLowerCase().includes(q) || t.text.toLowerCase().includes(q) || t.default.toLowerCase().includes(q)
        })
    }, [remote.data, query, filter, edits])

    if (remote.loading && !remote.data) return <Loading />
    if (!remote.data) return <ErrorBox error={remote.error} />

    const changed = remote.data.filter((t) => t.id in edits && edits[t.id] !== t.text)
    const setValue = (id: string, v: string) => setEdits((e) => ({ ...e, [id]: v }))

    return (
        <Card>
            <CardHeader>
                <CardTitle>متن‌های ربات</CardTitle>
                <CardDescription className="leading-6">
                    متن پیام‌ها و برچسب دکمه‌ها. HTML تلگرام (مثل &lt;b&gt;) پشتیبانی می‌شود. برای ایموجی پریمیوم، روی متن بزنید و از پنل «ایموجی پریمیوم» انتخاب کنید.
                    متغیرهای داخل {'{ }'} را نگه دارید؛ ربات موقع ارسال جای آن‌ها مقدار می‌گذارد. برچسب دکمه‌ها ایموجی پریمیوم نمی‌گیرند — آیکون دکمه را از بخش «دکمه‌ها» بگذارید.
                    تغییرها از پیام بعدی ربات اعمال می‌شوند.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                    <div className="relative min-w-[200px] flex-1">
                        <Search className="absolute right-3 top-3 h-4 w-4 text-muted-foreground" />
                        <Input
                            className="pr-9"
                            placeholder="جستجو در نام یا متن…"
                            value={query}
                            onChange={(e) => {
                                setQuery(e.target.value)
                                setShown(PAGE)
                            }}
                        />
                    </div>
                    <div className="flex gap-1 overflow-x-auto">
                        {FILTERS.map((f) => (
                            <button
                                key={f.key}
                                onClick={() => {
                                    setFilter(f.key)
                                    setShown(PAGE)
                                }}
                                className={cn(
                                    'shrink-0 rounded-lg px-3 py-2 text-xs',
                                    filter === f.key ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'
                                )}
                            >
                                {f.label}
                            </button>
                        ))}
                    </div>
                </div>
                <p className="text-xs text-muted-foreground">{list.length.toLocaleString('fa-IR')} متن</p>

                <EmojiBoard api={api}>
                    <div className="space-y-4">
                        {list.slice(0, shown).map((t) => {
                            const v = value(t)
                            const isDefault = v === t.default
                            return (
                                <div key={t.id} className="space-y-1.5 rounded-xl border border-border p-3">
                                    <div className="flex items-center gap-2">
                                        <code dir="ltr" className="text-xs font-semibold">
                                            {t.id}
                                        </code>
                                        {t.button && <span className="rounded bg-muted px-1.5 py-0.5 text-[10px]">دکمه</span>}
                                        {t.plain && <span className="rounded bg-muted px-1.5 py-0.5 text-[10px]">پیام کوتاه بدون قالب</span>}
                                        {!isDefault && (
                                            <Button
                                                size="sm"
                                                variant="ghost"
                                                className="mr-auto h-7 text-xs"
                                                title={t.default}
                                                onClick={() => setValue(t.id, t.default)}
                                            >
                                                <RotateCcw className="h-3.5 w-3.5 ml-1" /> متن پیش‌فرض
                                            </Button>
                                        )}
                                    </div>
                                    {t.button || t.plain ? (
                                        <Input value={v} onChange={(e) => setValue(t.id, e.target.value)} />
                                    ) : (
                                        <EmojiTextarea api={api} name={t.id} rows={3} value={v} onChange={(x) => setValue(t.id, x)} />
                                    )}
                                    {t.fields.length > 0 && (
                                        <p className="text-[11px] text-muted-foreground">
                                            متغیرها:{' '}
                                            <bdi dir="ltr">{t.fields.map((f) => `{${f}}`).join(' ')}</bdi>
                                        </p>
                                    )}
                                </div>
                            )
                        })}
                        {list.length > shown && (
                            <Button variant="outline" className="w-full" onClick={() => setShown((n) => n + PAGE)}>
                                نمایش بیشتر ({(list.length - shown).toLocaleString('fa-IR')} مورد دیگر)
                            </Button>
                        )}
                    </div>
                </EmojiBoard>

                <ErrorBox error={act.error} />
                <Notice text={act.notice} />
                <div className="sticky bottom-2 flex gap-2 rounded-xl bg-card/90 backdrop-blur p-2 border border-border">
                    <Button
                        disabled={act.busy || changed.length === 0}
                        onClick={async () => {
                            const res = await act.run(
                                () => api.put<TopupText[]>('texts', Object.fromEntries(changed.map((t) => [t.id, value(t)]))),
                                'ذخیره شد؛ از پیام بعدی ربات اعمال می‌شود'
                            )
                            if (res && res !== true) {
                                remote.setData(res as TopupText[])
                                setEdits({})
                            }
                        }}
                    >
                        {act.busy && <Spinner className="ml-2" />} ذخیره {changed.length ? `(${changed.length})` : ''}
                    </Button>
                    <Button variant="outline" disabled={!changed.length} onClick={() => setEdits({})}>
                        برگرداندن
                    </Button>
                </div>
            </CardContent>
        </Card>
    )
}
