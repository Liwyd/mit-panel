import { useEffect, useMemo, useRef, useState } from 'react'
import {
    Check,
    ChevronLeft,
    EyeOff,
    Eye,
    GripVertical,
    Info,
    Keyboard,
    LayoutTemplate,
    MessageSquareMore,
    Move,
    Pencil,
    RotateCcw,
    Sparkles,
    Trash2,
} from 'lucide-react'
import { BotAPI, BotButtons, EmojiPacks, botsAPI } from '@/lib/bots-api'
import { getUserRole } from '@/lib/auth'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import { ErrorBox, Loading, Notice, Spinner, selectClass, useAction, useLoad } from './common'
import { PremiumEmoji } from './emoji'
import { OtherButtons } from './OtherButtons'

type Style = { style?: string; emoji?: string; hidden?: boolean }
type Mode = 'reply' | 'inline'
type Target = { type: 'row'; row: number; index: number } | { type: 'gap'; at: number } | { type: 'tray' }

const MAX_PER_ROW = 3
const MAX_LABEL = 48
export const COLORS: Array<{ v: string; label: string; swatch: string; btn: string }> = [
    { v: '', label: 'خنثی', swatch: 'bg-slate-200', btn: 'bg-white text-slate-800 dark:bg-slate-700 dark:text-white' },
    { v: 'primary', label: 'آبی', swatch: 'bg-[#3e7be6]', btn: 'bg-[#3e7be6] text-white' },
    { v: 'success', label: 'سبز', swatch: 'bg-[#26a68a]', btn: 'bg-[#26a68a] text-white' },
    { v: 'danger', label: 'قرمز', swatch: 'bg-[#d9505a]', btn: 'bg-[#d9505a] text-white' },
]
export const btnClass = (style?: string) => (COLORS.find((c) => c.v === (style || '')) || COLORS[0]).btn
const DEFAULT_LAYOUT = [
    ['text_sell', 'text_usertest'],
    ['text_Purchased_services', 'text_Tariff_list'],
    ['text_account', 'text_Add_Balance'],
    ['affiliates'],
    ['text_support', 'text_help'],
]
const EXTRA_NAMES: Record<string, string> = {
    admin: 'پنل مدیریت (فقط ادمین‌ها)',
    text_Discount: 'کد هدیه',
    text_fq: 'سوالات متداول',
    support_message: 'ارسال پیام به پشتیبانی',
    rules_accept: 'پذیرش قوانین',
    back_home: 'بازگشت به منوی اصلی',
}
// Labels of these come from the bot's text table and can be renamed here.
const renameable = (k: string) => k.startsWith('text_')
const fa = (n: number) => n.toLocaleString('fa-IR')

export function ButtonsTab({ api, botKey, botName }: { api: BotAPI; botKey: string; botName: string }) {
    const remote = useLoad(() => api.get<BotButtons>('buttons'), [api])
    if (remote.loading && !remote.data) return <Loading />
    if (!remote.data) return <ErrorBox error={remote.error} />
    return (
        <div className="space-y-5">
            <ButtonsEditor api={api} botKey={botKey} botName={botName} d={remote.data} onSaved={remote.setData} />
            <OtherButtons api={api} botKey={botKey} />
        </div>
    )
}

function visibleRows(layout: string[][], styles: Record<string, Style>) {
    return layout.map((r) => r.filter((k) => !styles[k]?.hidden)).filter((r) => r.length > 0)
}

function ButtonsEditor({
    api,
    botKey,
    botName,
    d,
    onSaved,
}: {
    api: BotAPI
    botKey: string
    botName: string
    d: BotButtons
    onSaved: (b: BotButtons) => void
}) {
    const init = (x: BotButtons) => {
        const st: Record<string, Style> = JSON.parse(JSON.stringify(x.buttons || {}))
        return { mode: (x.mode || 'reply') as Mode, rows: visibleRows(x.layout, st), styles: st, labels: { ...x.labels } }
    }
    const [mode, setMode] = useState<Mode>(() => init(d).mode)
    const [rows, setRows] = useState<string[][]>(() => init(d).rows)
    const [styles, setStyles] = useState<Record<string, Style>>(() => init(d).styles)
    const [labels, setLabels] = useState<Record<string, string>>(() => init(d).labels)
    const [selected, setSelected] = useState<string | null>(null)
    const [drag, setDrag] = useState<{ key: string; x: number; y: number; target: Target | null; valid: boolean } | null>(null)
    const act = useAction()

    const editorRef = useRef<HTMLDivElement>(null)
    const choose = (k: string) => {
        setSelected(k)
        if (window.innerWidth < 1024) setTimeout(() => editorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
    }
    const st = (k: string): Style => styles[k] || {}
    const setSt = (k: string, v: Partial<Style>) => setStyles((s) => ({ ...s, [k]: { ...(s[k] || {}), ...v } }))
    const hiddenKeys = d.main_keys.filter((k) => st(k).hidden || !rows.some((r) => r.includes(k)))
    const isMain = (k: string) => d.main_keys.includes(k)

    // ------------------------------------------------------------ what gets saved
    const payload = () => {
        const clean: Record<string, Style> = {}
        for (const [k, v] of Object.entries(styles)) {
            const s: Style = {}
            if (v.style) s.style = v.style
            if (v.emoji && v.emoji.trim()) s.emoji = v.emoji.trim()
            if (v.hidden && isMain(k)) s.hidden = true
            if (Object.keys(s).length) clean[k] = s
        }
        // hidden buttons go to rows of their own at the end, so a row never
        // holds more than the bot allows
        const layout = [...rows.map((r) => [...r]), ...hiddenKeys.map((k) => [k])]
        return { mode, layout, buttons: clean }
    }
    const changedLabels = () => {
        const out: Record<string, string> = {}
        for (const [k, v] of Object.entries(labels)) if (renameable(k) && v.trim() && v !== d.labels[k]) out[k] = v
        return out
    }
    const original = useMemo(() => {
        const o = init(d)
        const clean: Record<string, Style> = {}
        for (const [k, v] of Object.entries(o.styles)) {
            const s: Style = {}
            if (v.style) s.style = v.style
            if (v.emoji) s.emoji = v.emoji
            if (v.hidden && d.main_keys.includes(k)) s.hidden = true
            if (Object.keys(s).length) clean[k] = s
        }
        const hidden = d.main_keys.filter((k) => clean[k]?.hidden || !o.rows.some((r) => r.includes(k)))
        return JSON.stringify({ mode: o.mode, layout: [...o.rows, ...hidden.map((k) => [k])], buttons: sortKeys(clean) })
    }, [d])
    const p = payload()
    const changes =
        (JSON.stringify({ mode: p.mode, layout: p.layout, buttons: sortKeys(p.buttons) }) !== original ? 1 : 0) + Object.keys(changedLabels()).length

    const save = async () => {
        const res = await act.run(async () => {
            const lbl = changedLabels()
            if (Object.keys(lbl).length) await api.put('texts', lbl)
            return api.put<BotButtons>('buttons', payload())
        }, 'ذخیره شد؛ کاربران با /start بعدی منوی جدید را می‌بینند')
        if (res && res !== true) onSaved(res as BotButtons)
    }
    const revertAll = () => {
        const o = init(d)
        setMode(o.mode)
        setRows(o.rows)
        setStyles(o.styles)
        setLabels(o.labels)
        setSelected(null)
    }

    // ------------------------------------------------------------ moving buttons
    const place = (key: string, t: Target) => {
        if (t.type === 'tray') {
            setRows((rs) => rs.map((r) => r.filter((k) => k !== key)).filter((r) => r.length))
            setSt(key, { hidden: true })
            return
        }
        setRows((rs) => {
            // keep emptied rows until the insert so indexes stay valid
            const next = rs.map((r) => r.filter((k) => k !== key))
            if (t.type === 'gap') next.splice(t.at, 0, [key])
            else if (t.row >= next.length) next.push([key])
            else next[t.row].splice(Math.min(t.index, next[t.row].length), 0, key)
            return next.filter((r) => r.length)
        })
        if (st(key).hidden) setSt(key, { hidden: false })
    }
    const position = (key: string): [number, number] => {
        for (let r = 0; r < rows.length; r++) {
            const c = rows[r].indexOf(key)
            if (c >= 0) return [r, c]
        }
        return [-1, -1]
    }
    // swap with the neighbour in reading order (row sizes stay the same)
    const shift = (key: string, dir: -1 | 1) => {
        const flat = rows.flat()
        const i = flat.indexOf(key)
        const j = i + dir
        if (i < 0 || j < 0 || j >= flat.length) return
        ;[flat[i], flat[j]] = [flat[j], flat[i]]
        let n = 0
        setRows(rows.map((r) => r.map(() => flat[n++])))
    }
    const roomIn = (row: number, key: string) => (rows[row] || []).filter((k) => k !== key).length < MAX_PER_ROW

    // ------------------------------------------------------------ drag & drop
    const phoneRef = useRef<HTMLDivElement>(null)
    const targetAt = (x: number, y: number, key: string): { target: Target | null; valid: boolean } => {
        const el = document.elementFromPoint(x, y)?.closest('[data-drop]') as HTMLElement | null
        if (!el) return { target: null, valid: false }
        const kind = el.dataset.drop
        if (kind === 'tray') return { target: { type: 'tray' }, valid: isMain(key) }
        if (kind === 'gap') return { target: { type: 'gap', at: Number(el.dataset.at) }, valid: true }
        if (kind === 'row') {
            const row = Number(el.dataset.row)
            const btns = Array.from(el.querySelectorAll<HTMLElement>('[data-btn]')).filter((b) => b.dataset.btn !== key)
            // right-to-left: buttons whose centre is right of the pointer come first
            const index = btns.filter((b) => {
                const r = b.getBoundingClientRect()
                return r.left + r.width / 2 > x
            }).length
            return { target: { type: 'row', row, index }, valid: roomIn(row, key) }
        }
        return { target: null, valid: false }
    }
    useEffect(() => {
        if (!drag) return
        const move = (e: PointerEvent) => {
            e.preventDefault()
            // scroll when the pointer nears the top or bottom edge
            if (e.clientY < 70) window.scrollBy(0, -16)
            else if (e.clientY > window.innerHeight - 70) window.scrollBy(0, 16)
            setDrag((dr) => (dr ? { ...dr, x: e.clientX, y: e.clientY, ...targetAt(e.clientX, e.clientY, dr.key) } : dr))
        }
        const up = () => {
            setDrag((dr) => {
                if (dr && dr.target && dr.valid) place(dr.key, dr.target)
                return null
            })
        }
        window.addEventListener('pointermove', move, { passive: false })
        window.addEventListener('pointerup', up)
        window.addEventListener('pointercancel', up)
        return () => {
            window.removeEventListener('pointermove', move)
            window.removeEventListener('pointerup', up)
            window.removeEventListener('pointercancel', up)
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [drag?.key])
    const startDrag = (key: string) => (e: React.PointerEvent) => {
        e.preventDefault()
        e.stopPropagation()
        setSelected(key)
        setDrag({ key, x: e.clientX, y: e.clientY, target: null, valid: false })
    }
    const over = (t: Target) =>
        !!drag?.target &&
        JSON.stringify(drag.target.type === 'row' ? { type: 'row', row: drag.target.row } : drag.target) ===
            JSON.stringify(t.type === 'row' ? { type: 'row', row: t.row } : t)

    // ------------------------------------------------------------ rendering
    const label = (k: string) => labels[k] || d.labels[k] || k
    const previewButton = (k: string, admin?: boolean) => (
        <div
            key={k}
            data-btn={k}
            onClick={() => choose(k)}
            className={cn(
                'group relative flex min-w-0 flex-1 cursor-pointer select-none items-center justify-center gap-1 rounded-lg px-1 py-2.5 text-[12px] font-semibold shadow-sm transition sm:px-2 sm:text-[13px]',
                btnClass(st(k).style),
                selected === k && 'ring-2 ring-amber-400 ring-offset-1 ring-offset-transparent',
                drag?.key === k && 'opacity-30'
            )}
        >
            {!admin && (
                <span
                    onPointerDown={startDrag(k)}
                    className="absolute left-0.5 top-1/2 -translate-y-1/2 cursor-grab touch-none rounded p-0.5 opacity-60 hover:opacity-100 active:cursor-grabbing sm:left-1"
                    aria-label="جابه‌جایی"
                >
                    <GripVertical className="h-4 w-4" />
                </span>
            )}
            {selected === k && <Pencil className="absolute right-1 top-1/2 h-3 w-3 -translate-y-1/2 opacity-80 sm:right-1.5 sm:h-3.5 sm:w-3.5" />}
            <PremiumEmoji api={api} botKey={botKey} id={st(k).emoji} />
            <span className="truncate px-3.5 sm:px-4">{label(k)}</span>
        </div>
    )
    const gap = (at: number) => (
        <div
            key={`gap-${at}`}
            data-drop="gap"
            data-at={at}
            className={cn(
                'h-2 rounded-md transition-colors',
                drag && over({ type: 'gap', at }) && 'bg-amber-400'
            )}
        />
    )
    const keyboard = (
        <div>
            {gap(0)}
            {rows.map((r, i) => (
                <div key={i}>
                    <div
                        data-drop="row"
                        data-row={i}
                        className={cn(
                            'flex gap-1.5 rounded-lg',
                            drag && over({ type: 'row', row: i, index: 0 }) && (drag.valid ? 'outline outline-2 outline-amber-400' : 'outline outline-2 outline-red-400')
                        )}
                    >
                        {r.map((k) => previewButton(k))}
                    </div>
                    {gap(i + 1)}
                </div>
            ))}
            <div className="flex">{previewButton('admin', true)}</div>
        </div>
    )

    const step = changes ? 3 : selected ? 2 : 1

    return (
        <div className="space-y-4">
            {/* display type */}
            <Card>
                <CardContent className="pt-5 space-y-3">
                    <div>
                        <div className="text-xs font-semibold text-primary">نوع نمایش</div>
                        <div className="font-bold">دکمه‌ها کجا دیده شوند؟</div>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <ModeOption
                            active={mode === 'reply'}
                            onClick={() => setMode('reply')}
                            icon={<Keyboard className="h-5 w-5" />}
                            title="منوی معمولی"
                            hint="ثابت در پایین تلگرام، جای کیبورد"
                        />
                        <ModeOption
                            active={mode === 'inline'}
                            onClick={() => setMode('inline')}
                            icon={<MessageSquareMore className="h-5 w-5" />}
                            title="منوی شیشه‌ای"
                            hint="متصل به پیام ربات"
                        />
                    </div>
                </CardContent>
            </Card>

            {/* steps */}
            <Card>
                <CardContent className="py-3">
                    <ol className="flex flex-wrap items-center justify-center gap-2 text-xs">
                        {[
                            ['انتخاب', 'روی یک دکمه بزنید'],
                            ['ویرایش', 'متن، رنگ و ردیف را عوض کنید'],
                            ['ذخیره', 'تغییرات را اعمال کنید'],
                        ].map(([t, h], i) => (
                            <li key={t} className="flex items-center gap-2">
                                {i > 0 && <ChevronLeft className="h-4 w-4 text-muted-foreground" />}
                                <span
                                    className={cn(
                                        'flex h-6 w-6 items-center justify-center rounded-md text-[11px] font-bold',
                                        step > i ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'
                                    )}
                                >
                                    {fa(i + 1)}
                                </span>
                                <span>
                                    <b className="block">{t}</b>
                                    <span className="text-muted-foreground">{h}</span>
                                </span>
                            </li>
                        ))}
                    </ol>
                </CardContent>
            </Card>

            <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 items-start">
                {/* preview */}
                <Card className="lg:col-span-3">
                    <CardContent className="pt-5 space-y-4">
                        <div className="flex flex-wrap items-start justify-between gap-2">
                            <div>
                                <div className="text-xs font-semibold text-primary">چیدمان</div>
                                <div className="font-bold">صفحه‌کلید مشتری</div>
                                <p className="text-xs text-muted-foreground">
                                    هر ردیف تا {fa(MAX_PER_ROW)} دکمه؛ دکمه را از دستگیره‌اش بگیرید و به ردیف دیگر یا بین ردیف‌ها بکشید.
                                </p>
                            </div>
                            <Button
                                size="sm"
                                variant="outline"
                                onClick={() => {
                                    setRows(DEFAULT_LAYOUT.map((r) => r.filter((k) => d.main_keys.includes(k) && !st(k).hidden)).filter((r) => r.length))
                                }}
                            >
                                <RotateCcw className="h-4 w-4 ml-1" /> چیدمان اولیه
                            </Button>
                        </div>

                        <div ref={phoneRef} className="mx-auto max-w-[400px] overflow-hidden rounded-[26px] border border-border shadow-xl">
                            <div className="flex items-center justify-between bg-[#3f7ea6] px-4 py-3 text-white" dir="rtl">
                                <span className="flex items-center gap-2">
                                    <ChevronLeft className="h-5 w-5 rotate-180" />
                                    <span>
                                        <b className="block text-sm">{botName || 'ربات فروش شما'}</b>
                                        <span className="text-[11px] opacity-80">آنلاین</span>
                                    </span>
                                </span>
                                <span className="text-lg leading-none">⋮</span>
                            </div>
                            <div className="flex min-h-[220px] flex-col justify-end bg-gradient-to-b from-[#d6e4ec] to-[#c9dbe5] p-3 dark:from-[#0e1621] dark:to-[#17212b]">
                                <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-white px-3 py-2 text-sm shadow-sm dark:bg-[#182533]">
                                    <div className="text-[11px] font-semibold text-[#3f7ea6]">ربات</div>
                                    از کدام بخش شروع کنیم؟
                                    <div className="text-left text-[10px] text-muted-foreground" dir="ltr">
                                        12:40 ✓
                                    </div>
                                </div>
                                {mode === 'inline' && <div className="mt-1.5 max-w-[95%]">{keyboard}</div>}
                            </div>
                            {mode === 'reply' && <div className="bg-[#e9eef2] p-2 dark:bg-[#1f2b38]">{keyboard}</div>}
                            <div className="flex items-center gap-2 border-t border-border bg-white px-3 py-2 text-sm text-muted-foreground dark:bg-[#17212b]">
                                <span className="flex-1 rounded-full bg-muted/60 px-3 py-1.5">پیام</span>
                                <Keyboard className={cn('h-4 w-4', mode === 'reply' && 'text-[#3f7ea6]')} />
                            </div>
                        </div>

                        <p className="flex items-start gap-2 rounded-lg bg-muted/40 p-2 text-xs text-muted-foreground">
                            <Info className="h-4 w-4 shrink-0" />
                            «پنل مدیریت» فقط برای ادمین‌ها نمایش داده می‌شود و همیشه ردیف آخر است. رنگ‌ها و آیکون‌ها در تلگرام ممکن است با تم
                            کاربر کمی فرق کنند.
                        </p>

                        {/* disabled tray */}
                        <div
                            data-drop="tray"
                            className={cn(
                                'rounded-xl border border-border p-3 space-y-2 transition',
                                drag && over({ type: 'tray' }) && 'border-dashed border-red-400 bg-red-50/50 dark:bg-red-950/20'
                            )}
                        >
                            <div className="flex items-center justify-between">
                                <span className="flex items-center gap-2">
                                    <EyeOff className="h-4 w-4 text-muted-foreground" />
                                    <span>
                                        <b className="block text-sm">دکمه‌های غیرفعال</b>
                                        <span className="text-xs text-muted-foreground">در منو نمایش داده نمی‌شوند. برای غیرفعال‌کردن، دکمه را این‌جا بکشید.</span>
                                    </span>
                                </span>
                                <span className="rounded-md bg-muted px-2 py-0.5 text-xs">{fa(hiddenKeys.length)}</span>
                            </div>
                            <div className="flex flex-wrap gap-2">
                                {hiddenKeys.map((k) => (
                                    <button
                                        key={k}
                                        onClick={() => choose(k)}
                                        className={cn(
                                            'flex items-center gap-2 rounded-lg border border-dashed border-border px-3 py-2 text-sm',
                                            selected === k && 'border-amber-400'
                                        )}
                                    >
                                        <span onPointerDown={startDrag(k)} className="cursor-grab touch-none">
                                            <GripVertical className="h-4 w-4 text-muted-foreground" />
                                        </span>
                                        {label(k)}
                                        <Eye className="h-4 w-4 text-muted-foreground" />
                                    </button>
                                ))}
                                {!hiddenKeys.length && <span className="text-xs text-muted-foreground">همه‌ی دکمه‌ها فعال‌اند.</span>}
                            </div>
                        </div>

                        <div className="space-y-2">
                            <b className="text-sm">دکمه‌های دیگر</b>
                            <p className="text-xs text-muted-foreground">دکمه‌هایی که داخل بخش‌های ربات می‌آیند؛ رنگ و آیکونشان را هم می‌شود عوض کرد.</p>
                            <div className="flex flex-wrap gap-2">
                                {d.extra_keys
                                    .filter((k) => k !== 'admin')
                                    .map((k) => (
                                        <button
                                            key={k}
                                            onClick={() => choose(k)}
                                            className={cn(
                                                'flex items-center gap-1 rounded-lg px-3 py-1.5 text-sm shadow-sm',
                                                btnClass(st(k).style),
                                                selected === k && 'ring-2 ring-amber-400'
                                            )}
                                        >
                                            <PremiumEmoji api={api} botKey={botKey} id={st(k).emoji} />
                                            {label(k)}
                                        </button>
                                    ))}
                            </div>
                        </div>
                    </CardContent>
                </Card>

                {/* editor */}
                <Card ref={editorRef} className="lg:col-span-2 lg:sticky lg:top-4 scroll-mt-4">
                    <CardContent className="pt-5">
                        {!selected ? (
                            <div className="py-10 text-center text-sm text-muted-foreground">
                                <LayoutTemplate className="mx-auto mb-2 h-8 w-8 opacity-50" />
                                روی یکی از دکمه‌های پیش‌نمایش بزنید تا ویرایشش کنید.
                            </div>
                        ) : (
                            <ButtonEditor
                                k={selected}
                                api={api}
                                botKey={botKey}
                                main={isMain(selected)}
                                name={EXTRA_NAMES[selected]}
                                style={st(selected)}
                                label={label(selected)}
                                savedLabel={d.labels[selected] || ''}
                                savedStyle={(d.buttons || {})[selected] || {}}
                                rows={rows}
                                hidden={hiddenKeys.includes(selected)}
                                pos={position(selected)}
                                onLabel={(v) => setLabels((l) => ({ ...l, [selected]: v }))}
                                onStyle={(v) => setSt(selected, v)}
                                onMoveRow={(r) => place(selected, r === -1 ? { type: 'gap', at: rows.length } : { type: 'row', row: r, index: 99 })}
                                roomIn={(r) => roomIn(r, selected)}
                                onShift={(dir) => shift(selected, dir)}
                                onHide={() => place(selected, { type: 'tray' })}
                                onShow={() => place(selected, { type: 'gap', at: rows.length })}
                            />
                        )}
                    </CardContent>
                </Card>
            </div>

            {/* save */}
            <div className="sticky bottom-2 z-10 flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card/95 p-3 shadow-lg backdrop-blur">
                <Button onClick={save} disabled={act.busy || !changes}>
                    {act.busy && <Spinner className="ml-2" />} ذخیره {changes ? `(${fa(changes)} تغییر)` : ''}
                </Button>
                <Button variant="outline" onClick={revertAll} disabled={act.busy || !changes}>
                    برگرداندن همه
                </Button>
                <div className="flex-1 min-w-[12rem]">
                    <ErrorBox error={act.error} />
                    <Notice text={act.notice} />
                </div>
            </div>

            {drag && (
                <div
                    className={cn(
                        'pointer-events-none fixed z-50 -translate-x-1/2 -translate-y-1/2 rounded-lg px-4 py-2 text-sm font-semibold shadow-2xl',
                        btnClass(st(drag.key).style),
                        drag.target && !drag.valid && 'ring-2 ring-red-500'
                    )}
                    style={{ left: drag.x, top: drag.y }}
                >
                    <Move className="ml-1 inline h-4 w-4" />
                    {label(drag.key)}
                </div>
            )}
        </div>
    )
}

function sortKeys<T>(o: Record<string, T>): Record<string, T> {
    return Object.fromEntries(Object.entries(o).sort(([a], [b]) => a.localeCompare(b)))
}

function ModeOption({ active, onClick, icon, title, hint }: { active: boolean; onClick: () => void; icon: React.ReactNode; title: string; hint: string }) {
    return (
        <button
            onClick={onClick}
            className={cn(
                'flex items-center justify-between gap-3 rounded-xl border p-3 text-right transition',
                active ? 'border-brand-green bg-brand-green/10' : 'border-border hover:bg-accent/50'
            )}
        >
            <span className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-lg border border-border bg-card">{icon}</span>
                <span>
                    <b className="block text-sm">{title}</b>
                    <span className="text-xs text-muted-foreground">{hint}</span>
                </span>
            </span>
            {active && (
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-brand-green text-white">
                    <Check className="h-3.5 w-3.5" />
                </span>
            )}
        </button>
    )
}

function ButtonEditor({
    k,
    api,
    botKey,
    main,
    name,
    style,
    label,
    savedLabel,
    savedStyle,
    rows,
    hidden,
    pos,
    onLabel,
    onStyle,
    onMoveRow,
    roomIn,
    onShift,
    onHide,
    onShow,
}: {
    k: string
    api: BotAPI
    botKey: string
    main: boolean
    name?: string
    style: Style
    label: string
    savedLabel: string
    savedStyle: Style
    rows: string[][]
    hidden: boolean
    pos: [number, number]
    onLabel: (v: string) => void
    onStyle: (v: Partial<Style>) => void
    onMoveRow: (row: number) => void
    roomIn: (row: number) => boolean
    onShift: (dir: -1 | 1) => void
    onHide: () => void
    onShow: () => void
}) {
    const [r, c] = pos
    return (
        <div className="space-y-5">
            <div>
                <div className="text-xs font-semibold text-primary">ویرایش</div>
                <div className="font-bold">دکمه‌ی انتخاب‌شده</div>
                <p className="text-xs text-muted-foreground">همه‌ی تغییرات را از همین بخش انجام دهید.</p>
            </div>
            <div className="flex items-center gap-3 rounded-xl bg-muted/40 p-3">
                <span className={cn('flex h-10 w-10 items-center justify-center rounded-lg text-lg', COLORS.find((x) => x.v === (style.style || ''))?.btn)}>
                    <PremiumEmoji api={api} botKey={botKey} id={style.emoji} fallback="◻" />
                </span>
                <span className="min-w-0">
                    <span className="block text-xs text-muted-foreground">{name || 'دکمه‌ی منوی اصلی'}</span>
                    <b className="block truncate">{label}</b>
                </span>
            </div>

            <div className="space-y-1.5">
                <b className="text-sm">متن روی دکمه</b>
                {renameable(k) ? (
                    <>
                        <div className="relative">
                            <Input value={label} maxLength={MAX_LABEL} onChange={(e) => onLabel(e.target.value)} className="pl-14" />
                            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground" dir="ltr">
                                {label.length}/{MAX_LABEL}
                            </span>
                        </div>
                        <p className="text-xs text-muted-foreground">ایموجی هم می‌توانید بگذارید؛ متن کوتاه‌تر روی موبایل خواناتر است.</p>
                    </>
                ) : (
                    <>
                        <Input value={label} disabled />
                        <p className="text-xs text-muted-foreground">متن این دکمه ثابت است؛ رنگ و آیکونش را می‌توانید عوض کنید.</p>
                    </>
                )}
            </div>

            <div className="space-y-2">
                <b className="text-sm">رنگ دکمه</b>
                <div className="grid grid-cols-4 gap-2">
                    {COLORS.map((x) => (
                        <button
                            key={x.v}
                            onClick={() => onStyle({ style: x.v })}
                            className={cn(
                                'flex flex-col items-center gap-1.5 rounded-xl border p-2 text-xs transition',
                                (style.style || '') === x.v ? 'border-primary ring-1 ring-primary' : 'border-border hover:bg-accent/50'
                            )}
                        >
                            <span className={cn('flex h-7 w-7 items-center justify-center rounded-md', x.swatch)}>
                                {(style.style || '') === x.v && <Check className={cn('h-4 w-4', x.v ? 'text-white' : 'text-slate-700')} />}
                            </span>
                            {x.label}
                        </button>
                    ))}
                </div>
                <p className="flex items-start gap-1.5 rounded-lg bg-[#3e7be6]/10 p-2 text-xs text-muted-foreground">
                    <Info className="h-3.5 w-3.5 shrink-0 mt-0.5" /> این چهار حالت رنگ‌های پشتیبانی‌شده‌ی تلگرام هستند و ممکن است با تم روشن یا تیره‌ی کاربر کمی متفاوت
                    دیده شوند.
                </p>
            </div>

            <EmojiPicker api={api} botKey={botKey} value={style.emoji || ''} onChange={(v) => onStyle({ emoji: v })} />

            {main && (
                <div className="space-y-3 rounded-xl border border-border p-3">
                    <div className="flex items-center justify-between">
                        <b className="flex items-center gap-1.5 text-sm">
                            <Move className="h-4 w-4 text-primary" /> جای دکمه
                        </b>
                        <span className="text-[11px] text-muted-foreground">بدون نیاز به کشیدن</span>
                    </div>
                    {hidden ? (
                        <p className="text-xs text-muted-foreground">این دکمه غیرفعال است؛ اول فعالش کنید.</p>
                    ) : (
                        <>
                            <label className="block space-y-1">
                                <span className="text-xs font-medium">انتقال به ردیف</span>
                                <select className={selectClass} value={r} onChange={(e) => onMoveRow(Number(e.target.value))}>
                                    {rows.map((row, i) => (
                                        <option key={i} value={i} disabled={i !== r && !roomIn(i)}>
                                            ردیف {fa(i + 1)} — {i === r ? `${fa(c + 1)} از ${fa(row.length)} دکمه` : `${fa(row.length)} دکمه`}
                                            {i !== r && !roomIn(i) ? ' (پر)' : ''}
                                        </option>
                                    ))}
                                    <option value={-1}>ردیف تازه (پایین)</option>
                                </select>
                            </label>
                            <div className="grid grid-cols-2 gap-2">
                                <Button variant="outline" size="sm" onClick={() => onShift(-1)}>
                                    → قبل‌تر
                                </Button>
                                <Button variant="outline" size="sm" onClick={() => onShift(1)}>
                                    بعدتر ←
                                </Button>
                            </div>
                        </>
                    )}
                </div>
            )}

            <div className="space-y-2 border-t border-border pt-4">
                {main &&
                    (hidden ? (
                        <Button variant="outline" className="w-full border-brand-green text-brand-green" onClick={onShow}>
                            <Eye className="h-4 w-4 ml-1" /> فعال‌کردن دوباره
                        </Button>
                    ) : (
                        <Button variant="outline" className="w-full border-destructive text-destructive hover:text-destructive" onClick={onHide}>
                            <EyeOff className="h-4 w-4 ml-1" /> غیرفعال‌کردن دکمه
                        </Button>
                    ))}
                <Button
                    variant="outline"
                    className="w-full"
                    onClick={() => {
                        onStyle({ style: savedStyle.style || '', emoji: savedStyle.emoji || '' })
                        if (renameable(k)) onLabel(savedLabel)
                    }}
                >
                    <RotateCcw className="h-4 w-4 ml-1" /> بازنشانی این دکمه
                </Button>
            </div>
        </div>
    )
}

// Only the packs the panel owner added (Bot page → پک‌های ایموجی) can be
// used; the bot refuses any other premium emoji too.
let packsCache: Promise<EmojiPacks> | null = null
export function loadPacks(fresh = false): Promise<EmojiPacks> {
    if (!packsCache || fresh) packsCache = botsAPI.packs().catch((e) => {
        packsCache = null
        throw e
    })
    return packsCache
}

export function EmojiPicker({ api, botKey, value, onChange }: { api: BotAPI; botKey: string; value: string; onChange: (v: string) => void }) {
    const packs = useLoad(() => loadPacks(), [])
    const [tab, setTab] = useState(0)
    const list = packs.data?.packs || []
    const inPacks = !value || list.some((p) => p.emojis.some((e) => e.id === value))
    const pack = list[Math.min(tab, Math.max(0, list.length - 1))]
    return (
        <div className="space-y-2 rounded-xl border border-border p-3">
            <b className="flex items-center gap-1.5 text-sm">
                <Sparkles className="h-4 w-4 text-amber-500" /> آیکون ایموجی پریمیوم
            </b>
            <p className="text-xs text-muted-foreground">
                ایموجی رنگی و متحرک کنار متن دکمه. فقط وقتی دیده می‌شود که صاحب ربات (اکانت سازنده در BotFather) تلگرام پریمیوم داشته باشد.
            </p>
            <div className="flex items-center gap-2">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-muted/50 text-xl">
                    {value ? <PremiumEmoji api={api} botKey={botKey} id={value} className="h-7 w-7" /> : <span className="text-xs text-muted-foreground">—</span>}
                </span>
                <span className="flex-1 text-xs text-muted-foreground">{value ? 'آیکون انتخاب‌شده' : 'بدون آیکون'}</span>
                {value && (
                    <Button size="sm" variant="ghost" onClick={() => onChange('')}>
                        <Trash2 className="h-4 w-4 ml-1 text-destructive" /> برداشتن
                    </Button>
                )}
            </div>
            {!inPacks && (
                <p className="rounded-lg bg-destructive/10 p-2 text-xs text-destructive">این آیکون در پک‌های مجاز نیست و در ربات نمایش داده نمی‌شود.</p>
            )}
            {packs.loading && !packs.data ? (
                <Loading />
            ) : !list.length ? (
                <p className="rounded-lg bg-muted/40 p-2 text-xs text-muted-foreground">
                    هنوز پک ایموجی‌ای برای ربات‌ها تعریف نشده است.{' '}
                    {getUserRole() === 'superadmin' ? 'از بخش «پک‌های ایموجی پریمیوم» بالای همین صفحه اضافه کنید.' : 'برای افزودن، لطفاً با پشتیبانی تماس بگیرید.'}
                </p>
            ) : (
                <>
                    {list.length > 1 && (
                        <div className="flex gap-1 overflow-x-auto pb-1">
                            {list.map((p, i) => (
                                <button
                                    key={p.name}
                                    onClick={() => setTab(i)}
                                    className={cn(
                                        'shrink-0 rounded-lg px-3 py-1 text-xs',
                                        pack?.name === p.name ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'
                                    )}
                                >
                                    {p.title}
                                </button>
                            ))}
                        </div>
                    )}
                    {pack && (
                        <div className="grid max-h-56 grid-cols-6 gap-1.5 overflow-y-auto rounded-lg bg-muted/30 p-2">
                            {pack.emojis.map((it) => (
                                <button
                                    key={it.id}
                                    title={it.emoji}
                                    onClick={() => onChange(it.id)}
                                    className={cn(
                                        'flex aspect-square items-center justify-center rounded-lg bg-card text-xl hover:ring-2 hover:ring-primary',
                                        value === it.id && 'ring-2 ring-primary'
                                    )}
                                >
                                    <PremiumEmoji api={api} botKey={botKey} id={it.id} fallback={it.emoji} className="h-7 w-7" />
                                </button>
                            ))}
                        </div>
                    )}
                </>
            )}
            <ErrorBox error={packs.error} />
        </div>
    )
}
