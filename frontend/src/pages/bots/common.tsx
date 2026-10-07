import { useCallback, useEffect, useRef, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Label } from '@/components/ui/label'

export function money(v: string | number | null | undefined): string {
    const n = Number(v || 0)
    if (!isFinite(n)) return String(v ?? '')
    return Math.round(n).toLocaleString('en-US') + ' تومان'
}

export function num(v: string | number | null | undefined): string {
    const n = Number(v || 0)
    return isFinite(n) ? n.toLocaleString('en-US') : String(v ?? '')
}

// Unix seconds (as the bot stores them) or a "Y/m/d H:i:s" string -> local text.
export function when(v: string | number | null | undefined): string {
    if (v === null || v === undefined || v === '') return '—'
    const s = String(v)
    if (/^\d{9,11}$/.test(s)) {
        return new Date(Number(s) * 1000).toLocaleString('fa-IR')
    }
    return s
}

export function errorText(err: unknown): string {
    if (err instanceof Error && err.message) return err.message
    return 'خطای ناشناخته'
}

// Load something once (and again on reload()), keeping the last good value.
export function useLoad<T>(load: () => Promise<T>, deps: React.DependencyList = []) {
    const [data, setData] = useState<T | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const loadRef = useRef(load)
    loadRef.current = load
    const reload = useCallback(async () => {
        setLoading(true)
        try {
            setData(await loadRef.current())
            setError(null)
        } catch (err) {
            setError(errorText(err))
        } finally {
            setLoading(false)
        }
    }, [])
    useEffect(() => {
        reload()
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, deps)
    return { data, setData, loading, error, reload }
}

// Run an action, show its error, and report busy state for the button.
export function useAction() {
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [notice, setNotice] = useState<string | null>(null)
    const run = useCallback(async <T,>(fn: () => Promise<T>, done?: string): Promise<T | true | null> => {
        setBusy(true)
        setError(null)
        setNotice(null)
        try {
            const result: T | true = (await fn()) ?? true
            if (done) setNotice(done)
            return result
        } catch (err) {
            setError(errorText(err))
            return null
        } finally {
            setBusy(false)
        }
    }, [])
    return { busy, error, notice, run, setError, setNotice }
}

export function Spinner({ className }: { className?: string }) {
    return <Loader2 className={cn('h-4 w-4 animate-spin', className)} />
}

export function Loading() {
    return (
        <div className="flex items-center justify-center py-12 text-muted-foreground">
            <Spinner className="h-6 w-6" />
        </div>
    )
}

export function ErrorBox({ error }: { error: string | null | undefined }) {
    if (!error) return null
    return (
        <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive border border-destructive/20" dir="auto">
            {error}
        </div>
    )
}

export function Notice({ text }: { text: string | null | undefined }) {
    if (!text) return null
    return (
        <div className="rounded-md bg-brand-green/10 p-3 text-sm text-brand-green border border-brand-green/20">{text}</div>
    )
}

export function Field({
    label,
    hint,
    children,
    className,
}: {
    label: string
    hint?: string
    children: React.ReactNode
    className?: string
}) {
    return (
        <div className={cn('space-y-1.5', className)}>
            <Label className="text-sm font-medium">{label}</Label>
            {children}
            {hint && <p className="text-xs text-muted-foreground leading-5">{hint}</p>}
        </div>
    )
}

export function Switch({
    checked,
    onChange,
    disabled,
    label,
    hint,
}: {
    checked: boolean
    onChange: (v: boolean) => void
    disabled?: boolean
    label: string
    hint?: string
}) {
    return (
        <label
            className={cn(
                'flex items-start justify-between gap-4 rounded-lg border border-border p-3 cursor-pointer select-none',
                disabled && 'opacity-60 cursor-not-allowed'
            )}
        >
            <span className="space-y-0.5">
                <span className="block text-sm font-medium">{label}</span>
                {hint && <span className="block text-xs text-muted-foreground leading-5">{hint}</span>}
            </span>
            <button
                type="button"
                role="switch"
                aria-checked={checked}
                disabled={disabled}
                onClick={() => onChange(!checked)}
                className={cn(
                    'relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors mt-0.5',
                    checked ? 'bg-primary' : 'bg-muted-foreground/30'
                )}
                dir="ltr"
            >
                <span
                    className={cn(
                        'inline-block h-5 w-5 rounded-full bg-white shadow transition-transform',
                        checked ? 'translate-x-[22px]' : 'translate-x-0.5'
                    )}
                />
            </button>
        </label>
    )
}

export function Stat({ label, value, sub }: { label: string; value: React.ReactNode; sub?: React.ReactNode }) {
    return (
        <div className="rounded-xl border border-border bg-card p-4">
            <div className="text-xs text-muted-foreground">{label}</div>
            <div className="mt-1 text-xl font-bold">{value}</div>
            {sub && <div className="mt-0.5 text-xs text-muted-foreground">{sub}</div>}
        </div>
    )
}

export function Empty({ text }: { text: string }) {
    return <p className="text-center text-sm text-muted-foreground py-8">{text}</p>
}

export const selectClass =
    'flex h-11 w-full rounded-lg border border-input bg-card px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'

// A bot's name is usually "@username": show it once, left-to-right (an RTL
// page would otherwise print "username@").
export function sameAsUsername(name: string, username?: string | null): boolean {
    return !!username && name.replace(/^@/, '').toLowerCase() === username.toLowerCase()
}

export function BotName({ name, username, usernameClass }: { name: string; username?: string | null; usernameClass?: string }) {
    return (
        <>
            <bdi dir="ltr">{name}</bdi>
            {username && !sameAsUsername(name, username) && (
                <bdi dir="ltr" className={usernameClass}>
                    @{username}
                </bdi>
            )}
        </>
    )
}
