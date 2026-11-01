import { createContext, forwardRef, useContext, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import { Smile } from 'lucide-react'
import { BotAPI } from '@/lib/bots-api'
import { getUserRole } from '@/lib/auth'
import { cn } from '@/lib/utils'
import { TextareaProps } from '@/components/ui/textarea'
import { ErrorBox, Loading, useLoad } from './common'
import { PremiumEmoji, previewURL } from './emoji'
import { loadPacks } from './ButtonsTab'

// A text box for a bot message with the allowed premium emoji packs next to
// it: a picked emoji goes in at the cursor and shows as itself; the text is
// kept as Telegram HTML with <tg-emoji emoji-id="…">…</tg-emoji>, which is
// how the bot sends it.

const TG_EMOJI = /<tg-emoji emoji-id="(\d+)">([\s\S]*?)<\/tg-emoji>/g

type Props = Omit<TextareaProps, 'value' | 'onChange'> & {
    api: BotAPI
    value: string
    onChange: (v: string) => void
    /** shown on the shared emoji panel while this box is the target */
    name?: string
}

export type Insert = (id: string, fallback: string) => void
type Board = { focus: (name: string, insert: Insert | null) => void }
const BoardContext = createContext<Board | null>(null)

// for other fields on the same page (button labels take the emoji as their icon)
export function useEmojiBoard() {
    return useContext(BoardContext)
}

// EmojiBoard puts one emoji panel beside a page of text boxes (sticky on wide
// screens): a pick goes into the box that was clicked last.
export function EmojiBoard({ api, children }: { api: BotAPI; children: React.ReactNode }) {
    const target = useRef<Insert | null>(null)
    const [name, setName] = useState('')
    const board = useMemo<Board>(
        () => ({
            focus: (n, insert) => {
                target.current = insert
                setName(insert ? n : '')
            },
        }),
        []
    )
    return (
        <BoardContext.Provider value={board}>
            <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
                <div className="min-w-0">{children}</div>
                <aside className="order-first lg:order-none">
                    <div className="space-y-2 lg:sticky lg:top-4">
                        <b className="flex items-center gap-1.5 text-sm">
                            <Smile className="h-4 w-4 text-amber-500" /> ایموجی پریمیوم
                        </b>
                        <p className="text-xs text-muted-foreground">
                            {name ? (
                                <>
                                    درج در: <b className="text-foreground">{name}</b>
                                </>
                            ) : (
                                'اول روی یک متن بزنید، بعد ایموجی را انتخاب کنید.'
                            )}
                        </p>
                        <Palette api={api} botKey={String(api.id)} onPick={(id, f) => target.current?.(id, f)} disabled={!name} />
                    </div>
                </aside>
            </div>
        </BoardContext.Provider>
    )
}

export function EmojiTextarea({ api, value, onChange, className, name, rows = 3, placeholder }: Props) {
    const board = useContext(BoardContext)
    const botKey = String(api.id)
    const editor = useRef<RichHandle>(null)
    const insert: Insert = (id, fallback) => editor.current?.insertEmoji(id, fallback)

    const box = (
        <RichText
            ref={editor}
            api={api}
            botKey={botKey}
            value={value}
            onChange={onChange}
            rows={rows}
            placeholder={placeholder}
            className={className}
            onFocus={() => board?.focus(name || 'این متن', insert)}
        />
    )
    if (board) return box
    // on its own: the packs stay open right beside the box
    return (
        <div className="grid gap-3 lg:grid-cols-[1fr_280px]">
            <div className="min-w-0">{box}</div>
            <div className="space-y-1.5">
                <b className="flex items-center gap-1.5 text-xs">
                    <Smile className="h-3.5 w-3.5 text-amber-500" /> ایموجی پریمیوم
                </b>
                <Palette api={api} botKey={botKey} onPick={insert} />
            </div>
        </div>
    )
}

// ---------------------------------------------------------------- the editor

// The text is edited with its premium emoji shown as the emoji themselves.
// Everything else stays plain text (Telegram HTML such as <b> is shown as
// typed); each emoji is an inline, non-editable chip that is written back as
// <tg-emoji emoji-id="…">fallback</tg-emoji>, so the stored text is the same
// as before.

type RichHandle = { insertEmoji: (id: string, fallback: string) => void }

const EMOJI_ATTR = 'data-emoji-id'

function escapeAttr(s: string) {
    return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;')
}

function emojiChip(api: BotAPI, botKey: string, id: string, fallback: string): HTMLElement {
    const chip = document.createElement('span')
    chip.setAttribute(EMOJI_ATTR, id)
    chip.dataset.fallback = fallback
    chip.contentEditable = 'false'
    chip.className = 'inline-block align-[-0.2em] mx-px'
    chip.textContent = fallback
    previewURL(api, botKey, id).then((url) => {
        if (!url) return
        const img = document.createElement('img')
        img.src = url
        img.alt = fallback
        img.draggable = false
        img.className = 'inline-block h-[1.25em] w-[1.25em] object-contain'
        img.onerror = () => {
            chip.textContent = fallback
        }
        chip.replaceChildren(img)
    })
    return chip
}

// the end marker keeps a trailing line break visible; it is not part of the text
function endMarker() {
    const br = document.createElement('br')
    br.dataset.end = '1'
    return br
}

function render(el: HTMLElement, api: BotAPI, botKey: string, text: string) {
    const nodes: Node[] = []
    let last = 0
    for (const m of text.matchAll(TG_EMOJI)) {
        if ((m.index ?? 0) > last) nodes.push(document.createTextNode(text.slice(last, m.index)))
        nodes.push(emojiChip(api, botKey, m[1], m[2]))
        last = (m.index ?? 0) + m[0].length
    }
    if (last < text.length) nodes.push(document.createTextNode(text.slice(last)))
    el.replaceChildren(...nodes, endMarker())
}

function serialize(el: Node): string {
    let out = ''
    el.childNodes.forEach((n) => {
        if (n.nodeType === Node.TEXT_NODE) {
            out += (n.textContent || '').replace(/\u200b/g, '')
            return
        }
        if (!(n instanceof HTMLElement)) return
        const id = n.getAttribute(EMOJI_ATTR)
        if (id) {
            out += `<tg-emoji emoji-id="${escapeAttr(id)}">${n.dataset.fallback || '⭐'}</tg-emoji>`
        } else if (n.tagName === 'BR') {
            if (!n.dataset.end) out += '\n'
        } else {
            // a line the browser wrapped in its own element
            if (n.tagName === 'DIV' || n.tagName === 'P') out += '\n'
            out += serialize(n)
        }
    })
    return out
}

const RichText = forwardRef<
    RichHandle,
    {
        api: BotAPI
        botKey: string
        value: string
        onChange: (v: string) => void
        rows: number
        placeholder?: string
        className?: string
        onFocus: () => void
    }
>(function RichText({ api, botKey, value, onChange, rows, placeholder, className, onFocus }, ref) {
    const el = useRef<HTMLDivElement>(null)
    const emitted = useRef<string | null>(null)
    const range = useRef<Range | null>(null)

    // remember the caret however it moves (mouse, keys, touch)
    useEffect(() => {
        const track = () => {
            const sel = window.getSelection()
            if (sel && sel.rangeCount && el.current?.contains(sel.anchorNode)) range.current = sel.getRangeAt(0).cloneRange()
        }
        document.addEventListener('selectionchange', track)
        return () => document.removeEventListener('selectionchange', track)
    }, [])

    // rebuild only when the text changed from outside (load, reset, save)
    useEffect(() => {
        if (el.current && value !== emitted.current) {
            render(el.current, api, botKey, value)
            emitted.current = value
        }
    }, [value, api, botKey])

    const emit = () => {
        if (!el.current) return
        const last = el.current.lastChild
        if (!(last instanceof HTMLElement && last.dataset.end)) el.current.appendChild(endMarker())
        const v = serialize(el.current)
        emitted.current = v
        onChange(v)
    }

    const keepRange = () => {
        const sel = window.getSelection()
        if (sel && sel.rangeCount && el.current?.contains(sel.anchorNode)) range.current = sel.getRangeAt(0).cloneRange()
    }

    // put a node where the caret is (or at the end) and move the caret after it
    const place = (node: Node) => {
        const box = el.current
        if (!box) return
        let r = range.current
        if (!r || !box.contains(r.startContainer)) {
            r = document.createRange()
            const end = box.lastChild
            if (end) r.setStartBefore(end)
            else r.setStart(box, 0)
            r.collapse(true)
        }
        r.deleteContents()
        r.insertNode(node)
        r.setStartAfter(node)
        r.collapse(true)
        const sel = window.getSelection()
        sel?.removeAllRanges()
        sel?.addRange(r)
        range.current = r.cloneRange()
        emit()
    }

    useImperativeHandle(ref, () => ({
        insertEmoji: (id, fallback) => {
            // focusing puts the caret at the start; keep where it was
            const saved = range.current
            el.current?.focus()
            range.current = saved
            place(emojiChip(api, botKey, id, fallback || '⭐'))
        },
    }))

    return (
        <div className="relative">
            {!value && placeholder && <span className="pointer-events-none absolute right-3 top-2 text-sm leading-7 text-muted-foreground">{placeholder}</span>}
            <div
                ref={el}
                role="textbox"
                aria-multiline="true"
                contentEditable
                suppressContentEditableWarning
                aria-placeholder={placeholder}
                onInput={emit}
                onFocus={onFocus}
                onKeyUp={keepRange}
                onMouseUp={keepRange}
                onBlur={keepRange}
                onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                        e.preventDefault()
                        keepRange()
                        place(document.createTextNode('\n'))
                    }
                }}
                onPaste={(e) => {
                    e.preventDefault()
                    keepRange()
                    place(document.createTextNode(e.clipboardData.getData('text/plain')))
                }}
                onDrop={(e) => e.preventDefault()}
                style={{ minHeight: `${rows * 1.75 + 1.25}rem` }}
                className={cn(
                    'w-full whitespace-pre-wrap break-words rounded-md border border-input bg-background px-3 py-2 text-sm leading-7 outline-none',
                    'focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ring-offset-background',
                    className
                )}
            />
        </div>
    )
})

function Palette({ api, botKey, onPick, disabled }: { api: BotAPI; botKey: string; onPick: Insert; disabled?: boolean }) {
    const packs = useLoad(() => loadPacks(), [])
    const [tab, setTab] = useState(0)
    const list = packs.data?.packs || []
    const pack = list[Math.min(tab, Math.max(0, list.length - 1))]
    if (packs.loading && !packs.data) return <Loading />
    if (!list.length)
        return (
            <p className="rounded-lg bg-muted/40 p-2 text-xs text-muted-foreground">
                هنوز پک ایموجی‌ای تعریف نشده است.{' '}
                {getUserRole() === 'superadmin' ? 'از بخش «پک‌های ایموجی پریمیوم» بالای صفحه اضافه کنید.' : 'برای افزودن، لطفاً با پشتیبانی تماس بگیرید.'}
            </p>
        )
    return (
        <div className="space-y-2 rounded-xl border border-border p-2">
            {list.length > 1 && (
                <div className="flex gap-1 overflow-x-auto pb-1">
                    {list.map((p, i) => (
                        <button
                            type="button"
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
                <div className={cn('grid max-h-64 grid-cols-7 gap-1 overflow-y-auto', disabled && 'pointer-events-none opacity-50')}>
                    {pack.emojis.map((e) => (
                        <button
                            type="button"
                            key={e.id}
                            title={e.emoji}
                            onMouseDown={(ev) => ev.preventDefault()}
                            onClick={() => onPick(e.id, e.emoji)}
                            className="flex aspect-square items-center justify-center rounded-lg bg-muted/30 text-xl hover:ring-2 hover:ring-primary"
                        >
                            <PremiumEmoji api={api} botKey={botKey} id={e.id} fallback={e.emoji} className="h-6 w-6" />
                        </button>
                    ))}
                </div>
            )}
            <p className="text-[11px] text-muted-foreground">روی هر ایموجی بزنید تا همان‌جای مکان‌نما در متن قرار بگیرد.</p>
            <ErrorBox error={packs.error} />
        </div>
    )
}
