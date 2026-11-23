import type { ReactNode } from 'react'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { fa, UNIT_GB, UNIT_TOMAN } from './format'

/** A number is an LTR island inside RTL text, so a minus sign stays beside its digits. */
export function Num({ children, className }: { children: ReactNode; className?: string }) {
    return (
        <bdi dir="ltr" className={cn('tabular-nums', className)}>
            {children}
        </bdi>
    )
}

export function Money({ value, className, unitClassName }: { value: number; className?: string; unitClassName?: string }) {
    return (
        <span className={className}>
            <Num>{fa(value)}</Num> <span className={cn('text-muted-foreground', unitClassName)}>{UNIT_TOMAN}</span>
        </span>
    )
}

export function Gb({ value, className }: { value: number; className?: string }) {
    return (
        <span className={className}>
            <Num>{fa(value)}</Num> <span className="text-muted-foreground">{UNIT_GB}</span>
        </span>
    )
}

/** A section that failed on the server: said quietly, in its own card only. */
export function Quiet({ children = 'این بخش در حال حاضر در دسترس نیست.' }: { children?: ReactNode }) {
    return <p className="pf-body py-6 text-center text-muted-foreground">{children}</p>
}

export function SectionCard({
    title,
    subtitle,
    action,
    children,
    className,
}: {
    title: string
    subtitle?: ReactNode
    action?: ReactNode
    children: ReactNode
    className?: string
}) {
    return (
        <Card className={cn('min-w-0 p-5 sm:p-6', className)}>
            <div className="mb-5 flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
                <div className="min-w-0">
                    <h2 className="text-base font-black leading-snug tracking-normal">{title}</h2>
                    {subtitle && <p className="pf-caption mt-0.5 text-muted-foreground">{subtitle}</p>}
                </div>
                {action}
            </div>
            {children}
        </Card>
    )
}

export function Skeleton({ className }: { className?: string }) {
    return <div className={cn('animate-pulse rounded-lg bg-muted', className)} />
}

/** The card-sized placeholder shown until the first response arrives. */
export function SkeletonCard({ height, className, compact }: { height: string; className?: string; compact?: boolean }) {
    if (compact) {
        return (
            <Card className={cn('p-4 sm:p-5', className)} style={{ height }} aria-hidden>
                <Skeleton className="h-3 w-16" />
                <Skeleton className="mt-3 h-6 w-28" />
                <Skeleton className="mt-3 h-3 w-24" />
            </Card>
        )
    }
    return (
        <Card className={cn('p-5 sm:p-6', className)} style={{ height }} aria-hidden>
            <Skeleton className="h-4 w-32" />
            <Skeleton className="mt-3 h-3 w-48" />
            <Skeleton className="mt-6 h-[calc(100%-4.5rem)] w-full" />
        </Card>
    )
}

export function Stat({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
    return (
        <div className={cn('min-w-0', className)}>
            <dt className="pf-caption text-muted-foreground">{label}</dt>
            <dd className="mt-0.5 text-lg font-bold leading-snug">{children}</dd>
        </div>
    )
}
