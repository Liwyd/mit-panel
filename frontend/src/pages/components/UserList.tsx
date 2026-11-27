/**
 * The sub-admin's user list.
 *
 * Each user is one row: clicking anywhere on it (or Enter/Space) opens or
 * closes its detail panel with a spring, and the everyday actions (QR, power,
 * edit, delete) sit on the row itself so they never need the panel.
 *
 * Motion: @react-spring/web drives the physical bits (panel height, caret,
 * press/hover on buttons, scroll reveal, traffic bar); anime.js staggers the
 * panel's contents in. Everything collapses to instant changes when the OS
 * asks for reduced motion.
 */
import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { animated, useInView, useReducedMotion, useSpring } from '@react-spring/web'
import { animate, stagger } from 'animejs'
import { toast } from 'sonner'
import {
    ArrowCounterClockwiseIcon,
    CalendarBlankIcon,
    CaretDownIcon,
    CheckIcon,
    CopyIcon,
    KeyIcon,
    LinkSimpleIcon,
    PencilSimpleLineIcon,
    PowerIcon,
    QrCodeIcon,
    TrashSimpleIcon,
    WifiHighIcon,
    type Icon,
} from '@phosphor-icons/react'
import { ClientsOutput } from '@/types'
import { bytesToGB } from '@/lib/traffic-converter'
import { cn, formatDate, formatExpiryWithDays } from '@/lib/utils'
import { buildSubUrl, lastOnlineInfo } from '@/lib/users'

// Snappy enough to feel like a direct response, damped enough not to wobble.
const PANEL_SPRING = { tension: 300, friction: 32 }
const PRESS_SPRING = { tension: 560, friction: 26 }

export interface UserListProps {
    users: ClientsOutput[]
    subUrl?: string
    onEdit: (user: ClientsOutput) => void
    onDelete: (user: ClientsOutput) => void
    onResetUsage: (user: ClientsOutput) => void
    onRevoke?: (user: ClientsOutput) => void
    onShowQr: (user: ClientsOutput) => void
    onToggleStatus: (user: ClientsOutput) => void
}

export function userKey(user: ClientsOutput) {
    return `${user.uuid || user.id}-${user.username}`
}

export function UserList({ users, ...actions }: UserListProps) {
    const [openKeys, setOpenKeys] = useState<Set<string>>(() => new Set())

    const toggle = (key: string) =>
        setOpenKeys((prev) => {
            const next = new Set(prev)
            if (next.has(key)) next.delete(key)
            else next.add(key)
            return next
        })

    return (
        <div className="space-y-2">
            <div className="hidden md:grid md:ul-grid px-5 pb-1 text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground/80">
                <span>User</span>
                <span>Traffic</span>
                <span>Expiry</span>
                <span className="sr-only">Actions</span>
                <span />
            </div>
            {users.map((user) => {
                const key = userKey(user)
                return (
                    <UserRow
                        key={key}
                        rowId={key}
                        user={user}
                        open={openKeys.has(key)}
                        onToggle={() => toggle(key)}
                        {...actions}
                    />
                )
            })}
        </div>
    )
}

interface UserRowProps extends Omit<UserListProps, 'users'> {
    rowId: string
    user: ClientsOutput
    open: boolean
    onToggle: () => void
}

function UserRow({
    rowId,
    user,
    open,
    onToggle,
    subUrl,
    onEdit,
    onDelete,
    onResetUsage,
    onRevoke,
    onShowQr,
    onToggleStatus,
}: UserRowProps) {
    const reduced = !!useReducedMotion()
    const online = lastOnlineInfo(user.online_at)
    const subLink = subUrl && user.sub_id ? buildSubUrl(subUrl, user.sub_id) : ''
    const panelId = `user-panel-${rowId.replace(/[^a-zA-Z0-9_-]/g, '_')}`

    // Rows rise into place the first time they scroll into view.
    const [revealRef, reveal] = useInView(
        () => ({
            from: { opacity: 0, y: 14 },
            to: { opacity: 1, y: 0 },
            config: { tension: 280, friction: 30 },
            immediate: reduced,
        }),
        { once: true, rootMargin: '0px 0px -6% 0px' },
    )
    const caret = useSpring({ rotate: open ? 180 : 0, config: PANEL_SPRING, immediate: reduced })

    const actionsBar = (
        <div className="pointer-events-auto relative z-10 flex items-center gap-1">
            {subLink && <IconAction icon={QrCodeIcon} label="QR code" onClick={() => onShowQr(user)} />}
            <IconAction
                icon={PowerIcon}
                label={user.status ? 'Disable user' : 'Enable user'}
                tone={user.status ? 'success' : 'muted'}
                onClick={() => onToggleStatus(user)}
            />
            <IconAction icon={PencilSimpleLineIcon} label="Edit user" onClick={() => onEdit(user)} />
            <IconAction icon={TrashSimpleIcon} label="Delete user" tone="danger" onClick={() => onDelete(user)} />
        </div>
    )

    return (
        <animated.div
            ref={revealRef}
            style={{
                opacity: reveal.opacity,
                transform: reveal.y.to((y) => (y === 0 ? 'none' : `translate3d(0, ${y}px, 0)`)),
            }}
            className={cn(
                'ul-row group/row relative overflow-hidden rounded-2xl border bg-card',
                'transition-[border-color,box-shadow] duration-300 ease-out',
                open
                    ? 'border-primary/25 shadow-[0_18px_44px_-22px_hsl(var(--primary)/0.45)]'
                    : 'border-border/70 hover:border-border hover:shadow-[0_14px_36px_-24px_rgba(0,0,0,0.35)]',
            )}
        >
            {/* Header: a full-size toggle button sits under the content, so a
                click anywhere on the strip opens the row; only the action
                buttons take their own clicks. */}
            <div className="relative">
            <button
                type="button"
                aria-expanded={open}
                aria-controls={panelId}
                aria-label={`${open ? 'Hide' : 'Show'} details for ${user.username}`}
                onClick={onToggle}
                className="absolute inset-0 z-0 w-full cursor-pointer rounded-2xl outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
            />
            <div
                className={cn(
                    'pointer-events-none relative px-4 py-3 md:px-5 md:py-3.5',
                    'grid gap-x-4 gap-y-3 grid-cols-[minmax(0,1fr)_auto] md:ul-grid md:items-center',
                )}
            >
                <Identity user={user} online={online.online} />

                {/* Mobile: caret top-right, beside the identity. */}
                <animated.span
                    style={{ transform: caret.rotate.to((r) => `rotate(${r}deg)`) }}
                    className="md:hidden self-center justify-self-end text-muted-foreground"
                    aria-hidden
                >
                    <CaretDownIcon size={18} weight="bold" />
                </animated.span>

                <div className="col-span-2 md:col-span-1">
                    <TrafficMeter used={user.used_data} limit={user.data_limit} reduced={reduced} />
                </div>

                <div className="hidden md:block">
                    <Expiry unix={user.expiry_date_unix} />
                </div>

                <div className="col-span-2 flex items-center justify-between md:col-span-1 md:justify-end">
                    <span className="md:hidden text-xs text-muted-foreground">
                        <Expiry unix={user.expiry_date_unix} compact />
                    </span>
                    {actionsBar}
                </div>

                <animated.span
                    style={{ transform: caret.rotate.to((r) => `rotate(${r}deg)`) }}
                    className="hidden md:flex h-8 w-8 items-center justify-center rounded-full text-muted-foreground transition-colors group-hover/row:text-foreground"
                    aria-hidden
                >
                    <CaretDownIcon size={16} weight="bold" />
                </animated.span>
            </div>
            </div>

            <Collapse id={panelId} open={open} reduced={reduced}>
                <div className="mx-4 mb-4 md:mx-5 rounded-xl border border-border/60 bg-gradient-to-b from-muted/50 to-muted/10 p-4 space-y-4">
                    <div className="flex flex-wrap gap-x-6 gap-y-2 text-xs" data-stagger>
                        <Meta
                            icon={WifiHighIcon}
                            label="Last online"
                            value={online.text}
                            accent={online.online ? 'text-emerald-500' : undefined}
                        />
                        <span className="md:hidden">
                            <Meta icon={CalendarBlankIcon} label="Expiry" value={<Expiry unix={user.expiry_date_unix} inline />} />
                        </span>
                    </div>

                    {subLink && (
                        <div data-stagger>
                            <SubscriptionField link={subLink} />
                        </div>
                    )}

                    <div className="flex flex-wrap gap-2" data-stagger>
                        <PillAction icon={ArrowCounterClockwiseIcon} onClick={() => onResetUsage(user)}>
                            Reset usage
                        </PillAction>
                        {onRevoke && (
                            <PillAction icon={KeyIcon} onClick={() => onRevoke(user)}>
                                Revoke subscription
                            </PillAction>
                        )}
                    </div>
                </div>
            </Collapse>
        </animated.div>
    )
}

/* ------------------------------------------------------------------ pieces */

function Identity({ user, online }: { user: ClientsOutput; online: boolean }) {
    const tone = online ? 'online' : user.status ? 'active' : 'inactive'
    return (
        <div className="flex min-w-0 items-center gap-3">
            <span className="relative shrink-0">
                <span className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-muted to-secondary text-sm font-semibold uppercase text-foreground/80 ring-1 ring-border/70">
                    {user.username.slice(0, 1)}
                </span>
                <span
                    className={cn(
                        'absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full ring-2 ring-card',
                        tone === 'online' && 'bg-emerald-500',
                        tone === 'active' && 'bg-foreground/30',
                        tone === 'inactive' && 'bg-destructive',
                    )}
                >
                    {tone === 'online' && (
                        <span className="absolute inset-0 rounded-full bg-emerald-500 opacity-60 motion-safe:animate-ping" />
                    )}
                </span>
            </span>
            <div className="min-w-0">
                <div className="truncate font-mono text-sm font-medium tracking-tight">{user.username}</div>
                <StatusText tone={tone} />
            </div>
        </div>
    )
}

function StatusText({ tone }: { tone: 'online' | 'active' | 'inactive' }) {
    const label = { online: 'Online', active: 'Active', inactive: 'Inactive' }[tone]
    return (
        <div
            className={cn(
                'text-[11px] font-medium tracking-wide',
                tone === 'online' && 'text-emerald-500',
                tone === 'active' && 'text-muted-foreground',
                tone === 'inactive' && 'text-destructive',
            )}
        >
            {label}
        </div>
    )
}

function TrafficMeter({ used, limit, reduced }: { used: number; limit: number; reduced: boolean }) {
    const unlimited = !limit || limit <= 0
    const ratio = unlimited ? 0 : Math.min(used / limit, 1)
    const bar = useSpring({ from: { p: 0 }, to: { p: ratio }, config: { tension: 170, friction: 26 }, immediate: reduced })

    return (
        <div className="space-y-1.5">
            <div className="flex items-baseline gap-1 text-sm tabular-nums">
                <span className="font-medium">{bytesToGB(used).toFixed(2)}</span>
                <span className="text-muted-foreground">/ {unlimited ? '∞' : bytesToGB(limit).toFixed(2)} GB</span>
            </div>
            {!unlimited && (
                <div className="h-1 w-full max-w-[9rem] overflow-hidden rounded-full bg-muted">
                    <animated.div
                        className={cn(
                            'h-full w-full origin-left rounded-full',
                            ratio >= 0.95 ? 'bg-destructive' : ratio >= 0.8 ? 'bg-amber-500' : 'bg-foreground/55',
                        )}
                        style={{ transform: bar.p.to((p) => `scaleX(${p})`) }}
                    />
                </div>
            )}
        </div>
    )
}

function Expiry({ unix, compact = false, inline = false }: { unix: number | null; compact?: boolean; inline?: boolean }) {
    if (!unix) return <span className="text-sm text-muted-foreground">No expiry</span>
    const info = formatExpiryWithDays(unix)
    const tone = info.isExpired ? 'text-destructive' : info.daysLeft <= 7 ? 'text-amber-500' : 'text-muted-foreground'
    if (compact) return <span className={tone}>{info.text}</span>
    if (inline) {
        return (
            <span className="tabular-nums">
                {formatDate(unix)} <span className={cn('font-normal', tone)}>· {info.text}</span>
            </span>
        )
    }
    return (
        <div className="space-y-0.5">
            <div className="text-sm tabular-nums">{formatDate(unix)}</div>
            <div className={cn('text-xs', tone)}>{info.text}</div>
        </div>
    )
}

function Meta({ icon: I, label, value, accent }: { icon: Icon; label: string; value: ReactNode; accent?: string }) {
    return (
        <span className="inline-flex items-center gap-2">
            <I size={15} weight="duotone" className={cn('text-muted-foreground', accent)} />
            <span className="text-muted-foreground">{label}</span>
            <span className={cn('font-medium text-foreground', accent)}>{value}</span>
        </span>
    )
}

function SubscriptionField({ link }: { link: string }) {
    const [copied, setCopied] = useState(false)
    const iconRef = useRef<HTMLSpanElement>(null)

    const copy = async () => {
        try {
            await navigator.clipboard.writeText(link)
        } catch {
            toast.error('Could not copy — select the link and copy it manually')
            return
        }
        setCopied(true)
        if (iconRef.current) animate(iconRef.current, { scale: [0.5, 1], duration: 420, ease: 'outBack' })
        window.setTimeout(() => setCopied(false), 1600)
    }

    return (
        <div className="flex items-center gap-3 rounded-lg border border-border/70 bg-card px-3 py-2">
            <LinkSimpleIcon size={16} weight="duotone" className="shrink-0 text-muted-foreground" />
            <div className="min-w-0 flex-1">
                <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground">Subscription</div>
                <div className="truncate font-mono text-xs select-all" title={link}>
                    {link}
                </div>
            </div>
            <PressButton
                onClick={copy}
                aria-label={copied ? 'Copied' : 'Copy subscription link'}
                className={cn(
                    'inline-flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-xs font-medium transition-colors',
                    copied
                        ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                        : 'border-border bg-background hover:bg-muted',
                )}
            >
                <span ref={iconRef} className="inline-flex">
                    {copied ? <CheckIcon size={14} weight="bold" /> : <CopyIcon size={14} weight="duotone" />}
                </span>
                {copied ? 'Copied' : 'Copy'}
            </PressButton>
        </div>
    )
}

/* ------------------------------------------------------------- interaction */

/** A button that dips when pressed and lifts on hover, on a spring. */
function PressButton({
    children,
    className,
    onClick,
    lift = 1.04,
    ...rest
}: {
    children: ReactNode
    className?: string
    onClick: () => void
    lift?: number
    'aria-label'?: string
    title?: string
}) {
    const reduced = !!useReducedMotion()
    const [s, api] = useSpring(() => ({ scale: 1, config: PRESS_SPRING }))
    const to = (scale: number) => {
        if (!reduced) api.start({ scale })
    }
    return (
        <animated.button
            type="button"
            style={{ transform: s.scale.to((v) => (v === 1 ? 'none' : `scale(${v})`)) }}
            onPointerEnter={() => to(lift)}
            onPointerLeave={() => to(1)}
            onPointerDown={() => to(0.9)}
            onPointerUp={() => to(lift)}
            onClick={(e) => {
                e.stopPropagation()
                onClick()
            }}
            className={cn(
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-card',
                className,
            )}
            {...rest}
        >
            {children}
        </animated.button>
    )
}

function IconAction({
    icon: I,
    label,
    onClick,
    tone = 'neutral',
}: {
    icon: Icon
    label: string
    onClick: () => void
    tone?: 'neutral' | 'danger' | 'success' | 'muted'
}) {
    const [hover, setHover] = useState(false)
    return (
        <span onPointerEnter={() => setHover(true)} onPointerLeave={() => setHover(false)} className="inline-flex">
            <PressButton
                onClick={onClick}
                aria-label={label}
                title={label}
                lift={1.1}
                className={cn(
                    'inline-flex h-9 w-9 items-center justify-center rounded-xl transition-colors duration-200',
                    tone === 'neutral' && 'text-foreground/70 hover:bg-muted hover:text-foreground',
                    tone === 'success' && 'text-emerald-500 hover:bg-emerald-500/10',
                    tone === 'muted' && 'text-muted-foreground/60 hover:bg-muted hover:text-foreground',
                    tone === 'danger' && 'text-foreground/70 hover:bg-destructive/10 hover:text-destructive',
                )}
            >
                <I size={18} weight={hover ? 'duotone' : 'regular'} />
            </PressButton>
        </span>
    )
}

function PillAction({ icon: I, children, onClick }: { icon: Icon; children: ReactNode; onClick: () => void }) {
    return (
        <PressButton
            onClick={onClick}
            className="inline-flex h-9 items-center gap-2 rounded-full border border-border/80 bg-card px-4 text-xs font-medium text-foreground/80 shadow-sm transition-colors hover:border-primary/40 hover:text-foreground"
        >
            <I size={15} weight="duotone" />
            {children}
        </PressButton>
    )
}

/**
 * Animates its children's height between 0 and their natural size. The content
 * is only in the DOM while open or closing, so a long list stays light.
 */
function Collapse({ id, open, reduced, children }: { id: string; open: boolean; reduced: boolean; children: ReactNode }) {
    const innerRef = useRef<HTMLDivElement>(null)
    const [height, setHeight] = useState(0)
    // True from the moment an open starts until a close comes to rest, so the
    // content stays in the DOM while it animates shut.
    const [shown, setShown] = useState(open)
    const rendered = open || shown

    // Measure asynchronously; the observer also fires once on attach.
    useLayoutEffect(() => {
        const el = innerRef.current
        if (!el) return
        const ro = new ResizeObserver(([entry]) => setHeight(entry.borderBoxSize?.[0]?.blockSize ?? el.offsetHeight))
        ro.observe(el)
        return () => ro.disconnect()
    }, [rendered])

    // Stagger the panel's sections in each time it opens.
    useLayoutEffect(() => {
        const el = innerRef.current
        if (!open || reduced || !el) return
        const targets = el.querySelectorAll<HTMLElement>('[data-stagger]')
        if (!targets.length) return
        const anim = animate(targets, {
            opacity: [0, 1],
            translateY: [8, 0],
            delay: stagger(45, { start: 60 }),
            duration: 460,
            ease: 'outQuint',
        })
        return () => {
            anim.revert()
        }
    }, [open, reduced])

    const spring = useSpring({
        height: open ? height : 0,
        opacity: open ? 1 : 0,
        config: PANEL_SPRING,
        immediate: reduced,
        onStart: () => {
            if (open) setShown(true)
        },
        onRest: () => {
            if (!open) setShown(false)
        },
    })

    return (
        <animated.div
            id={id}
            role="region"
            aria-hidden={!open}
            style={{ height: spring.height, opacity: spring.opacity, overflow: 'hidden' }}
        >
            {rendered && <div ref={innerRef}>{children}</div>}
        </animated.div>
    )
}
