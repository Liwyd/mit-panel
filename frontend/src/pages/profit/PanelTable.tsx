import { useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Search } from 'lucide-react'
import type { ProfitAdminRow } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { fa, faPercent } from './format'
import { Num } from './parts'

const PAGE_SIZE = 10

type SortKey = 'username' | 'gb_sold' | 'avg_price_per_gb' | 'revenue' | 'cost' | 'profit' | 'margin'

const COLUMNS: { key: SortKey; label: string; numeric: boolean }[] = [
    { key: 'username', label: 'پنل', numeric: false },
    { key: 'gb_sold', label: 'گیگ فروخته‌شده', numeric: true },
    { key: 'avg_price_per_gb', label: 'میانگین قیمت هر گیگ', numeric: true },
    { key: 'revenue', label: 'درآمد', numeric: true },
    { key: 'cost', label: 'هزینه', numeric: true },
    { key: 'profit', label: 'سود', numeric: true },
    { key: 'margin', label: 'حاشیه سود', numeric: true },
]

const displayName = (row: ProfitAdminRow) => (row.username === '—' ? 'بدون پنل' : row.username)

export function PanelTable({ rows }: { rows: ProfitAdminRow[] }) {
    const [query, setQuery] = useState('')
    const [sortKey, setSortKey] = useState<SortKey>('profit')
    const [descending, setDescending] = useState(true)
    const [page, setPage] = useState(1)

    const filtered = useMemo(() => {
        const needle = query.trim().toLowerCase()
        const matching = needle ? rows.filter((r) => displayName(r).toLowerCase().includes(needle)) : rows
        const direction = descending ? -1 : 1
        return [...matching].sort((a, b) => {
            if (sortKey === 'username') return direction * displayName(a).localeCompare(displayName(b))
            // A missing value (no price, no margin) sorts as the lowest.
            const left = a[sortKey] ?? -Infinity
            const right = b[sortKey] ?? -Infinity
            return direction * (left === right ? 0 : left > right ? 1 : -1)
        })
    }, [rows, query, sortKey, descending])

    const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
    const current = Math.min(page, pages)
    const visible = filtered.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE)

    const sortBy = (key: SortKey) => {
        if (key === sortKey) setDescending((d) => !d)
        else {
            setSortKey(key)
            setDescending(key !== 'username')
        }
        setPage(1)
    }

    return (
        <div className="space-y-4">
            <div className="relative max-w-sm">
                <Search className="pointer-events-none absolute start-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                    value={query}
                    onChange={(e) => {
                        setQuery(e.target.value)
                        setPage(1)
                    }}
                    placeholder="جستجوی پنل"
                    aria-label="جستجوی پنل"
                    className="ps-10"
                />
            </div>

            <Table>
                <TableHeader>
                    <TableRow className="hover:bg-transparent">
                        {COLUMNS.map((col) => {
                            const active = col.key === sortKey
                            return (
                                <TableHead
                                    key={col.key}
                                    className={cn('whitespace-nowrap px-3', col.numeric ? 'text-end' : 'text-start')}
                                    aria-sort={active ? (descending ? 'descending' : 'ascending') : 'none'}
                                >
                                    <button
                                        type="button"
                                        onClick={() => sortBy(col.key)}
                                        className={cn(
                                            'pf-body inline-flex items-center gap-1 rounded-md py-1 font-bold transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                                            active ? 'text-foreground' : 'text-muted-foreground'
                                        )}
                                    >
                                        {col.label}
                                        {active &&
                                            (descending ? (
                                                <ArrowDown className="h-3.5 w-3.5" />
                                            ) : (
                                                <ArrowUp className="h-3.5 w-3.5" />
                                            ))}
                                    </button>
                                </TableHead>
                            )
                        })}
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {visible.map((row) => (
                        <TableRow key={row.username}>
                            <TableCell className="pf-body whitespace-nowrap px-3 text-start font-bold">{displayName(row)}</TableCell>
                            <TableCell className="pf-body whitespace-nowrap px-3 text-end">
                                <Num>{fa(row.gb_sold)}</Num>
                            </TableCell>
                            <TableCell className="pf-body whitespace-nowrap px-3 text-end">
                                {row.avg_price_per_gb === null ? '—' : <Num>{fa(row.avg_price_per_gb)}</Num>}
                            </TableCell>
                            <TableCell className="pf-body whitespace-nowrap px-3 text-end">
                                <Num>{fa(row.revenue)}</Num>
                            </TableCell>
                            <TableCell className="pf-body whitespace-nowrap px-3 text-end">
                                <Num>{fa(row.cost)}</Num>
                            </TableCell>
                            <TableCell
                                className={cn(
                                    'pf-body whitespace-nowrap px-3 text-end font-bold',
                                    row.profit < 0 && 'text-destructive'
                                )}
                            >
                                <Num>{fa(row.profit)}</Num>
                            </TableCell>
                            <TableCell
                                className={cn(
                                    'pf-body whitespace-nowrap px-3 text-end',
                                    row.margin !== null && row.margin < 0 && 'text-destructive'
                                )}
                            >
                                <Num>{faPercent(row.margin)}</Num>
                            </TableCell>
                        </TableRow>
                    ))}
                    {visible.length === 0 && (
                        <TableRow className="hover:bg-transparent">
                            <TableCell colSpan={COLUMNS.length} className="pf-body py-8 text-center text-muted-foreground">
                                {rows.length === 0 ? 'در این ماه فروشی ثبت نشده است.' : 'پنلی با این نام پیدا نشد.'}
                            </TableCell>
                        </TableRow>
                    )}
                </TableBody>
            </Table>

            <div className="flex items-center justify-between gap-3">
                <span className="pf-body text-muted-foreground">
                    صفحه <Num>{fa(current)}</Num> از <Num>{fa(pages)}</Num>
                    <span className="mx-2">·</span>
                    <Num>{fa(filtered.length)}</Num> پنل
                </span>
                <div className="flex gap-2">
                    {/* In RTL the "previous" page is toward the right. */}
                    <Button
                        variant="outline"
                        size="sm"
                        disabled={current <= 1}
                        onClick={() => setPage(current - 1)}
                        className="gap-1"
                    >
                        <ChevronRight className="h-4 w-4" />
                        قبلی
                    </Button>
                    <Button
                        variant="outline"
                        size="sm"
                        disabled={current >= pages}
                        onClick={() => setPage(current + 1)}
                        className="gap-1"
                    >
                        بعدی
                        <ChevronLeft className="h-4 w-4" />
                    </Button>
                </div>
            </div>
        </div>
    )
}
