import { useEffect, useState } from 'react'
import {
    Zap,
    Users,
    ChevronDown,
    ChevronLeft,
    ChevronRight,
    Plus,
    Edit2,
    Trash2,
    RotateCcw,
    UserX,
    ExternalLink,
    Server,
    Clock,
    Wifi,
    Copy,
    Check,
    QrCode,
    Search,
    Power,
} from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { dashboardAPI, userAPI } from '@/lib/api'
import { bytesToGB, formatTraffic } from '@/lib/traffic-converter'
import { formatDate, formatExpiryWithDays, cn } from '@/lib/utils'
import { getUserRole } from '@/lib/auth'
import { DashboardData, ClientsOutput, MarzbanOverview, MarzbanPeriod, MARZBAN_PERIODS } from '@/types'
import { Donut, Gauge, SEGMENT_COLORS } from '@/components/charts/Donut'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogHeader,
    AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import { UserFormDialog } from './components/UserFormDialog'

    function buildSubUrl(subUrl?: string, subId?: string) {
        if (!subUrl || !subId) return ''

        if (subId.startsWith('http://') || subId.startsWith('https://')) {
            return subId
        }

        const cleanBase = subUrl.replace(/\/+$/, '')
        const cleanId = subId.replace(/^\/+/, '')

        return `${cleanBase}/${cleanId}`
    }


function lastOnlineInfo(onlineAt?: string | null): { online: boolean; text: string } {
    if (!onlineAt) return { online: false, text: 'Never online' }
    const iso = /[zZ]|[+-]\d\d:?\d\d$/.test(onlineAt) ? onlineAt : onlineAt + 'Z'
    const t = new Date(iso).getTime()
    if (isNaN(t)) return { online: false, text: '—' }
    const diff = Date.now() - t
    if (diff < 60000) return { online: true, text: 'Online' }
    const m = Math.floor(diff / 60000)
    if (m < 60) return { online: false, text: `${m}m ago` }
    const h = Math.floor(m / 60)
    if (h < 24) return { online: false, text: `${h}h ago` }
    const d = Math.floor(h / 24)
    return { online: false, text: `${d}d ago` }
}

function CopyButton({
    text,
    label,
    iconClassName = 'h-4 w-4 mr-2',
    className,
    onClickCapture,
}: {
    text: string
    label: string
    iconClassName?: string
    className?: string
    onClickCapture?: (e: React.MouseEvent) => void
}) {
    const [copied, setCopied] = useState(false)
    return (
        <Button
            size="sm"
            variant="outline"
            className={cn(
                'transition-colors',
                copied && 'border-emerald-500 text-emerald-500 hover:text-emerald-500',
                className
            )}
            onClick={(e) => {
                onClickCapture?.(e)
                navigator.clipboard.writeText(text)
                setCopied(true)
                setTimeout(() => setCopied(false), 1500)
            }}
        >
            {copied ? <Check className={iconClassName} /> : <Copy className={iconClassName} />}
            {copied ? 'Copied!' : label}
        </Button>
    )
}

interface ExpandedRow {
    [key: string]: boolean
}

export function DashboardPage() {
    const [dashboardData, setDashboardData] = useState<DashboardData | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [expandedRows, setExpandedRows] = useState<ExpandedRow>({})
    const [selectedUser, setSelectedUser] = useState<ClientsOutput | null>(null)
    const [showUserDialog, setShowUserDialog] = useState(false)
    const [userToDelete, setUserToDelete] = useState<string | null>(null)
    const [showQrDialog, setShowQrDialog] = useState(false)
    const [qrUser, setQrUser] = useState<ClientsOutput | null>(null)
    const [currentPage, setCurrentPage] = useState(1)
    const [searchQuery, setSearchQuery] = useState('')
    const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'inactive' | 'online'>('all')
    const [marzban, setMarzban] = useState<MarzbanOverview | null>(null)
    const [marzbanPeriod, setMarzbanPeriod] = useState<MarzbanPeriod>('1d')
    const [usersPerPage, setUsersPerPage] = useState(() => {
        const saved = localStorage.getItem('usersPerPage')
        return saved ? parseInt(saved, 10) : 5
    })

    // Save usersPerPage to localStorage whenever it changes
    useEffect(() => {
        localStorage.setItem('usersPerPage', usersPerPage.toString())
    }, [usersPerPage])

    const userRole = getUserRole()

    useEffect(() => {
        fetchDashboardData()
    }, [])

    // Marzban's own figures: refetched when the window changes, then kept warm
    // on a slow timer. The backend caches the online scan, so this stays cheap.
    useEffect(() => {
        if (userRole !== 'superadmin') return

        let cancelled = false

        const load = async () => {
            try {
                const overview = await dashboardAPI.getMarzbanOverview(marzbanPeriod)
                if (!cancelled) setMarzban(overview)
            } catch (err) {
                console.warn('Failed to fetch Marzban overview:', err)
            }
        }

        load()
        const interval = setInterval(load, 30000)

        return () => {
            cancelled = true
            clearInterval(interval)
        }
    }, [userRole, marzbanPeriod])

    // Auto-refresh system info every 5 seconds for superadmin
    useEffect(() => {
        if (userRole !== 'superadmin') return

        const interval = setInterval(async () => {
            try {
                const systemInfo = await dashboardAPI.getSystemInfo()
                setDashboardData((prevData) =>
                    prevData ? { ...prevData, system: systemInfo } : null
                )
            } catch (err) {
                console.warn('Failed to refresh system info:', err)
            }
        }, 5000) // 5 seconds

        return () => clearInterval(interval)
    }, [userRole])

    const fetchDashboardData = async () => {
        try {
            setLoading(true)
            const data = await dashboardAPI.getDashboardData()

            // Fetch system info if user is superadmin
            if (userRole === 'superadmin') {
                try {
                    const systemInfo = await dashboardAPI.getSystemInfo()
                    data.system = systemInfo
                } catch (err) {
                    console.warn('Failed to fetch system info:', err)
                }
            }

            setDashboardData(data)
            setError(null)
        } catch (err: any) {
            console.error('Failed to fetch dashboard data:', err)
            setError(err?.message || 'Failed to fetch dashboard data')
        } finally {
            setLoading(false)
        }
    }

    const handleDeleteUser = async () => {
        if (!userToDelete) return

        try {
            // userToDelete format: "uuid|username|id"
            const [uuid, username, id] = userToDelete.split('|')
            await userAPI.deleteUser(uuid, username, id)
            setUserToDelete(null)
            fetchDashboardData()
        } catch (err: any) {
            console.error('Failed to delete user:', err)
            alert(err?.message || 'Failed to delete user')
        }
    }

    const handleResetUsage = async (email: string) => {
        try {
            await userAPI.resetUserUsage(email)
            fetchDashboardData()
        } catch (err: any) {
            console.error('Failed to reset usage:', err)
            alert(err?.message || 'Failed to reset usage')
        }
    }

    const handleToggleStatus = async (user: ClientsOutput) => {
        try {
            // Toggle status only: the expiry timestamp is forwarded untouched
            // (as epoch ms, not a date string) so enabling/disabling a user
            // never moves their expiry date.
            await userAPI.updateUser(
                user.uuid || '0',
                user.username,
                user.data_limit / (1024 ** 3), // Convert back to GB
                user.expiry_date_unix || null,
                user.sub_id || '',
                !user.status, // Toggle status
                user.flow || '',
                user.id?.toString()
            )
            fetchDashboardData()
        } catch (err: any) {
            console.error('Failed to toggle status:', err)
            alert(err?.message || 'Failed to toggle user status')
        }
    }

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
            </div>
        )
    }

    return (
        <div className="space-y-6 p-4 md:p-6 max-w-full overflow-x-hidden">
            {/* Page Title */}
            <div>
                <h1 className="text-2xl md:text-3xl font-bold tracking-tight">Dashboard</h1>
                <p className="text-muted-foreground">Welcome back!</p>
            </div>

            {/* Error Message */}
            {error && (
                <div className="rounded-md bg-destructive/10 p-4 text-sm text-destructive border border-destructive/20">
                    {error}
                </div>
            )}

            {/* Marzban Overview - superadmin only */}
            {userRole === 'superadmin' && marzban && (
                <div className="space-y-4">
                    {/* Headline rings */}
                    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                        <Card>
                            <CardContent className="flex items-center gap-4 p-5">
                                <Donut
                                    size={104}
                                    thickness={13}
                                    segments={[
                                        { label: 'Active', value: marzban.users.active },
                                        {
                                            label: 'Inactive',
                                            value: Math.max(0, marzban.users.total - marzban.users.active),
                                            color: 'hsl(var(--muted-foreground) / 0.25)',
                                        },
                                    ]}
                                />
                                <div className="min-w-0">
                                    <p className="text-xs font-extrabold text-muted-foreground">Active Users</p>
                                    <p className="text-2xl font-black tabular leading-tight">
                                        {marzban.users.active.toLocaleString()}
                                        <span className="text-base font-bold text-muted-foreground">
                                            {' / '}{marzban.users.total.toLocaleString()}
                                        </span>
                                    </p>
                                </div>
                            </CardContent>
                        </Card>

                        <Card>
                            <CardContent className="flex items-center gap-4 p-5">
                                <Donut
                                    size={104}
                                    thickness={13}
                                    segments={[
                                        { label: 'Online', value: marzban.users.online ?? 0, color: 'hsl(var(--brand-blue))' },
                                        {
                                            label: 'Offline',
                                            value: Math.max(0, marzban.users.total - (marzban.users.online ?? 0)),
                                            color: 'hsl(var(--muted-foreground) / 0.25)',
                                        },
                                    ]}
                                />
                                <div className="min-w-0">
                                    <p className="text-xs font-extrabold text-muted-foreground">Online Users</p>
                                    <p className="text-2xl font-black tabular leading-tight">
                                        {marzban.users.online === null ? '-' : marzban.users.online.toLocaleString()}
                                    </p>
                                    <p className="text-xs text-muted-foreground">Across all nodes</p>
                                </div>
                            </CardContent>
                        </Card>

                        <Card>
                            <CardContent className="flex items-center gap-4 p-5">
                                <Donut
                                    size={104}
                                    thickness={13}
                                    segments={[
                                        { label: 'Download', value: marzban.traffic.outgoing, color: 'hsl(var(--brand-green))' },
                                        { label: 'Upload', value: marzban.traffic.incoming, color: 'hsl(var(--brand-gold))' },
                                    ]}
                                />
                                <div className="min-w-0">
                                    <p className="text-xs font-extrabold text-muted-foreground">Data Usage</p>
                                    <p className="text-2xl font-black tabular leading-tight">
                                        {formatTraffic(marzban.traffic.total)}
                                    </p>
                                    <p className="text-xs text-muted-foreground">
                                        Down {formatTraffic(marzban.traffic.outgoing)} / Up {formatTraffic(marzban.traffic.incoming)}
                                    </p>
                                </div>
                            </CardContent>
                        </Card>

                        <Card>
                            <CardContent className="flex items-center gap-4 p-5">
                                <Donut
                                    size={104}
                                    thickness={13}
                                    segments={[
                                        { label: 'Used', value: marzban.memory.used, color: 'hsl(var(--brand-blue))' },
                                        {
                                            label: 'Free',
                                            value: Math.max(0, marzban.memory.total - marzban.memory.used),
                                            color: 'hsl(var(--muted-foreground) / 0.25)',
                                        },
                                    ]}
                                />
                                <div className="min-w-0">
                                    <p className="text-xs font-extrabold text-muted-foreground">Marzban Memory</p>
                                    <p className="text-2xl font-black tabular leading-tight">
                                        {bytesToGB(marzban.memory.used).toFixed(1)}
                                        <span className="text-base font-bold text-muted-foreground">
                                            {' / '}{bytesToGB(marzban.memory.total).toFixed(1)} GB
                                        </span>
                                    </p>
                                    <p className="text-xs text-muted-foreground">
                                        CPU {marzban.cpu.usage.toFixed(1)}% - {marzban.cpu.cores} cores
                                    </p>
                                </div>
                            </CardContent>
                        </Card>
                    </div>

                    {/* Nodes usage */}
                    <Card>
                        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                            <CardTitle className="text-base">Nodes Usage</CardTitle>
                            <div className="flex flex-wrap gap-1 rounded-xl bg-muted p-1">
                                {MARZBAN_PERIODS.map((period) => (
                                    <button
                                        key={period}
                                        type="button"
                                        onClick={() => setMarzbanPeriod(period)}
                                        className={cn(
                                            'min-w-11 rounded-lg px-3 py-1.5 text-xs font-extrabold transition-colors',
                                            marzbanPeriod === period
                                                ? 'bg-brand-blue text-white shadow-sm'
                                                : 'text-muted-foreground hover:text-foreground'
                                        )}
                                    >
                                        {period}
                                    </button>
                                ))}
                            </div>
                        </CardHeader>
                        <CardContent>
                            {marzban.nodes.items.length === 0 ? (
                                <p className="py-8 text-center text-sm text-muted-foreground">
                                    No node traffic recorded in this window.
                                </p>
                            ) : (
                                <div className="flex flex-col items-center gap-8 md:flex-row md:justify-center">
                                    <Donut
                                        segments={marzban.nodes.items.map((node) => ({
                                            label: node.name,
                                            value: node.usage,
                                        }))}
                                        centerLabel={formatTraffic(marzban.nodes.total)}
                                        centerCaption="Total"
                                    />

                                    <div className="w-full max-w-sm space-y-2">
                                        {marzban.nodes.items.map((node, index) => {
                                            const share = marzban.nodes.total
                                                ? (node.usage / marzban.nodes.total) * 100
                                                : 0
                                            return (
                                                <div
                                                    key={`${node.name}-${index}`}
                                                    className="flex items-center gap-3 rounded-lg px-2 py-1.5"
                                                >
                                                    <span
                                                        className="h-3 w-3 shrink-0 rounded-full"
                                                        style={{
                                                            backgroundColor:
                                                                SEGMENT_COLORS[index % SEGMENT_COLORS.length],
                                                        }}
                                                    />
                                                    <span className="min-w-0 flex-1 truncate text-sm font-bold">
                                                        {node.name}
                                                    </span>
                                                    <span className="tabular text-sm font-extrabold">
                                                        {formatTraffic(node.usage)}
                                                    </span>
                                                    <span className="tabular w-12 text-left text-xs text-muted-foreground">
                                                        {share.toFixed(1)}%
                                                    </span>
                                                </div>
                                            )
                                        })}
                                    </div>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </div>
            )}

            {/* SuperAdmin Stats Row */}
            {userRole === 'superadmin' && dashboardData && (
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {/* Total Panels */}
                    {dashboardData.panels && (
                        <Card>
                            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                <CardTitle className="text-sm font-medium">Total Panels</CardTitle>
                                <Server className="h-4 w-4 text-primary" />
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold">{dashboardData.panels.length}</div>
                                <p className="text-xs text-muted-foreground">Configured panels</p>
                            </CardContent>
                        </Card>
                    )}

                    {/* Total Active Admins */}
                    {dashboardData.admins && (
                        <Card>
                            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                <CardTitle className="text-sm font-medium">Total Active Admins</CardTitle>
                                <Users className="h-4 w-4 text-green-500" />
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold">
                                    {dashboardData.admins.filter(a => a.is_active).length}
                                </div>
                                <p className="text-xs text-muted-foreground">Active administrators</p>
                            </CardContent>
                        </Card>
                    )}

                    {/* Total Inactive Admins */}
                    {dashboardData.admins && (
                        <Card>
                            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                <CardTitle className="text-sm font-medium">Total Inactive Admins</CardTitle>
                                <UserX className="h-4 w-4 text-red-500" />
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold text-destructive">
                                    {dashboardData.admins.filter(a => !a.is_active).length}
                                </div>
                                <p className="text-xs text-muted-foreground">Inactive administrators</p>
                            </CardContent>
                        </Card>
                    )}
                </div>
            )}

            {/* System Stats Row - panel host resources */}
            {dashboardData?.system && (
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-base">Panel Server</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-2 gap-6 py-2 lg:grid-cols-4">
                            <Gauge
                                percent={dashboardData.system.cpu_percent}
                                label="CPU"
                                caption={
                                    dashboardData.system.cpu_cores
                                        ? `${dashboardData.system.cpu_cores} Cores`
                                        : undefined
                                }
                            />
                            <Gauge
                                percent={
                                    dashboardData.system.total_memory
                                        ? (dashboardData.system.used_memory / dashboardData.system.total_memory) * 100
                                        : 0
                                }
                                label="RAM"
                                caption={`${bytesToGB(dashboardData.system.used_memory).toFixed(2)} GB / ${bytesToGB(dashboardData.system.total_memory).toFixed(2)} GB`}
                            />
                            <Gauge
                                percent={
                                    dashboardData.system.swap_total
                                        ? ((dashboardData.system.swap_used || 0) / dashboardData.system.swap_total) * 100
                                        : 0
                                }
                                label="Swap"
                                caption={
                                    dashboardData.system.swap_total
                                        ? `${((dashboardData.system.swap_used || 0) / (1024 ** 2)).toFixed(2)} MB / ${(dashboardData.system.swap_total / (1024 ** 2)).toFixed(2)} MB`
                                        : 'Not configured'
                                }
                            />
                            <Gauge
                                percent={
                                    dashboardData.system.disk_total
                                        ? (dashboardData.system.disk_used / dashboardData.system.disk_total) * 100
                                        : 0
                                }
                                label="Storage"
                                caption={`${bytesToGB(dashboardData.system.disk_used).toFixed(2)} GB / ${bytesToGB(dashboardData.system.disk_total).toFixed(2)} GB`}
                            />
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Admin News - Only for admin role */}
            {userRole === 'admin' && dashboardData?.news && dashboardData.news.length > 0 && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-sm font-medium flex items-center gap-2">
                            <Zap className="h-4 w-4 text-primary" />
                            News & Updates
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                        {dashboardData.news.map((newsItem, index) => (
                            <div
                                key={index}
                                className="flex items-start gap-2 p-2 rounded-md hover:bg-muted/20 transition-colors duration-150"
                                style={{ direction: /[\u0600-\u06FF]/.test(newsItem) ? 'rtl' : 'ltr' }}
                            >
                                <Zap className="h-4 w-4 text-primary mt-1 flex-shrink-0" />
                                <div className="text-sm text-muted-foreground break-words">{newsItem}</div>
                            </div>
                        ))}
                    </CardContent>
                </Card>
            )}



            {/* Admin Stats Row - Only for admin role */}
            {userRole === 'admin' && dashboardData && (
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                    {/* Remaining Traffic */}
                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-medium">Remaining Traffic</CardTitle>
                            <Zap className="h-4 w-4 text-primary" />
                        </CardHeader>
                        <CardContent>
                            <div className="text-2xl font-bold">
                                {dashboardData.remaining_traffic !== undefined
                                    ? dashboardData.initial_traffic !== undefined
                                        ? `${bytesToGB(dashboardData.remaining_traffic).toFixed(2)} / ${bytesToGB(dashboardData.initial_traffic).toFixed(2)} GB`
                                        : `${bytesToGB(dashboardData.remaining_traffic).toFixed(2)} GB`
                                    : 'N/A'}
                            </div>
                            <p className="text-xs text-muted-foreground">
                                {dashboardData.remaining_traffic !== undefined
                                    ? dashboardData.initial_traffic !== undefined
                                        ? 'Remaining / Initial traffic'
                                        : formatTraffic(dashboardData.remaining_traffic)
                                    : 'No data'}
                            </p>
                        </CardContent>
                    </Card>

                    {/* Expiry Date */}
                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-medium">Expiry Date</CardTitle>
                            <Clock className="h-4 w-4 text-primary" />
                        </CardHeader>
                        <CardContent>
                            <div className="text-2xl font-bold">
                                {dashboardData.expiry_time
                                    ? formatDate(dashboardData.expiry_time)
                                    : 'No expiry'}
                            </div>
                            <p className="text-xs text-muted-foreground">Account expiration</p>
                        </CardContent>
                    </Card>

                    {/* Total Users */}
                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-medium">Total Users</CardTitle>
                            <Users className="h-4 w-4 text-green-500" />
                        </CardHeader>
                        <CardContent>
                            <div className="text-2xl font-bold">
                                {dashboardData.users?.length || 0}
                            </div>
                            <p className="text-xs text-muted-foreground">Registered users</p>
                        </CardContent>
                    </Card>

                    {/* Online Users */}
                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-medium">Online Users</CardTitle>
                            <Wifi className="h-4 w-4 text-emerald-500" />
                        </CardHeader>
                        <CardContent>
                            <div className="text-2xl font-bold text-emerald-500">
                                {dashboardData.users?.filter(u => lastOnlineInfo(u.online_at).online).length || 0}
                            </div>
                            <p className="text-xs text-muted-foreground">Currently connected</p>
                        </CardContent>
                    </Card>
                </div>
            )}

            {/* Advertisement Card */}
            {dashboardData?.ads && dashboardData.ads.text && (
                <Card className="bg-primary/5 border-primary/30 relative">
                    <CardContent className="p-4 pt-8">
                        <a
                            href={dashboardData.ads.link || '#'}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="block group"
                        >
                            <div className="flex flex-col gap-2" dir="rtl">
                                <div className="flex-1 min-w-0" dir="rtl">
                                    {dashboardData.ads.title && (
                                        <h3 className="font-bold text-primary text-sm mb-1 group-hover:text-primary/80 transition-colors" dir="rtl">
                                            {dashboardData.ads.title}
                                        </h3>
                                    )}
                                    <p className="text-sm text-muted-foreground leading-relaxed group-hover:text-foreground transition-colors" dir="rtl">
                                        {dashboardData.ads.text}
                                    </p>
                                    {dashboardData.ads.button && (
                                        <div className="mt-3 flex justify-start">
                                            <span className="inline-flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground text-sm font-semibold rounded-lg transition-all duration-200 transform hover:scale-105" dir="rtl">
                                                <ExternalLink className="h-4 w-4" />
                                                {dashboardData.ads.button}
                                            </span>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </a>
                    </CardContent>
                </Card>
            )}

            {/* Users Table */}
            {dashboardData?.users && (
                <Card>
                    <CardHeader className="flex flex-col gap-4">
                        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                            <div>
                                <CardTitle>Your Users</CardTitle>
                            </div>
                            <Button
                                size="sm"
                                onClick={() => {
                                    setSelectedUser(null)
                                    setShowUserDialog(true)
                                }}
                            >
                                <Plus className="h-4 w-4 mr-2" />
                                Add User
                            </Button>
                        </div>

                        {/* Search Bar and Filter */}
                        <div className="flex flex-col sm:flex-row gap-3">
                            <select
                                value={statusFilter}
                                onChange={(e) => {
                                    setStatusFilter(e.target.value as 'all' | 'active' | 'inactive' | 'online')
                                    setCurrentPage(1)
                                }}
                                className="h-10 w-auto rounded-md border border-input bg-background px-3 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                            >
                                <option value="all">All</option>
                                <option value="active">Active</option>
                                <option value="inactive">Inactive</option>
                                <option value="online">Online</option>
                            </select>
                            <div className="relative flex-1">
                                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                                <Input
                                    type="text"
                                    placeholder="Search users by email or username..."
                                    value={searchQuery}
                                    onChange={(e) => {
                                        setSearchQuery(e.target.value)
                                        setCurrentPage(1)
                                    }}
                                    className="pl-10"
                                />
                            </div>
                        </div>
                    </CardHeader>

                    <CardContent>
                        {(() => {
                            // Filter users based on search query and status
                            const filteredUsers = dashboardData.users.filter(user => {
                                // Search filter
                                const matchesSearch = user.username.toLowerCase().includes(searchQuery.toLowerCase()) ||
                                    (user.uuid && user.uuid.toLowerCase().includes(searchQuery.toLowerCase()))
                                
                                if (!matchesSearch) return false
                                
                                // Status filter
                                if (statusFilter === 'all') return true
                                if (statusFilter === 'online') return lastOnlineInfo(user.online_at).online
                                if (statusFilter === 'active') return user.status && !lastOnlineInfo(user.online_at).online
                                if (statusFilter === 'inactive') return !user.status
                                
                                return true
                            })

                            if (filteredUsers.length === 0) {
                                return (
                                    <div className="text-center py-8">
                                        <p className="text-muted-foreground">
                                            {searchQuery || statusFilter !== 'all' 
                                                ? 'No users found matching your filters' 
                                                : 'No users yet'}
                                        </p>
                                    </div>
                                )
                            }

                            const reversedUsers = [...filteredUsers].reverse()
                            const paginatedUsers = reversedUsers.slice(
                                (currentPage - 1) * usersPerPage,
                                currentPage * usersPerPage
                            )

                            return (
                                <>
                                    {/* Mobile View - Cards */}
                                    <div className="md:hidden space-y-3">
                                        {paginatedUsers.map((user) => {
                                            const userKey = `${user.uuid || user.id}-${user.username}`
                                            return (
                                                <MobileUserCard
                                                    key={`mobile-${userKey}`}
                                                    user={user}
                                                    isExpanded={expandedRows[userKey] || false}
                                                    subUrl={dashboardData.sub_url}
                                                    onToggle={() => {
                                                        setExpandedRows(prev => ({
                                                            ...prev,
                                                            [userKey]: !prev[userKey],
                                                        }))
                                                    }}
                                                    onEdit={() => {
                                                        setSelectedUser(user)
                                                        setShowUserDialog(true)
                                                    }}
                                                    onDelete={() => setUserToDelete(`${user.uuid || '0'}|${user.username}|${user.id}`)}
                                                    onResetUsage={() => handleResetUsage(user.username)}
                                                    onShowQr={(user) => {
                                                        setQrUser(user)
                                                        setShowQrDialog(true)
                                                    }}
                                                    onToggleStatus={() => handleToggleStatus(user)}
                                                />
                                            )
                                        })}
                                    </div>

                                    {/* Desktop View - Table */}
                                    <div className="hidden md:block overflow-x-auto">
                                        <Table>
                                            <TableHeader>
                                                <TableRow>
                                                    <TableHead className="w-12"></TableHead>
                                                    <TableHead>Email</TableHead>
                                                    <TableHead>Traffic</TableHead>
                                                    <TableHead>Expiry</TableHead>
                                                    <TableHead>Status</TableHead>
                                                    <TableHead className="text-right">Actions</TableHead>
                                                </TableRow>
                                            </TableHeader>
                                            <TableBody>
                                                {paginatedUsers.map((user) => {
                                                    const userKey = `${user.uuid || user.id}-${user.username}`
                                                    return (
                                                        <DetailsRow
                                                            key={`desktop-${userKey}`}
                                                            user={user}
                                                            isExpanded={expandedRows[userKey] || false}
                                                            subUrl={dashboardData.sub_url}
                                                            onToggle={() => {
                                                                setExpandedRows(prev => ({
                                                                    ...prev,
                                                                    [userKey]: !prev[userKey],
                                                                }))
                                                            }}
                                                            onEdit={() => {
                                                                setSelectedUser(user)
                                                                setShowUserDialog(true)
                                                            }}
                                                            onDelete={() => setUserToDelete(`${user.uuid || '0'}|${user.username}|${user.id}`)}
                                                            onResetUsage={() => handleResetUsage(user.username)}
                                                            onShowQr={(user) => {
                                                                setQrUser(user)
                                                                setShowQrDialog(true)
                                                            }}
                                                            onToggleStatus={() => handleToggleStatus(user)}
                                                        />
                                                    )
                                                })}
                                            </TableBody>
                                        </Table>
                                    </div>

                                    {/* Pagination */}
                                    {filteredUsers.length > 0 && (
                                        <div className="flex flex-col sm:flex-row items-center justify-between pt-4 border-t mt-4 gap-3">
                                            <div className="flex items-center gap-3">
                                                <p className="text-sm text-muted-foreground text-center sm:text-left">
                                                    Showing {((currentPage - 1) * usersPerPage) + 1} to {Math.min(currentPage * usersPerPage, filteredUsers.length)} of {filteredUsers.length}
                                                    {searchQuery && dashboardData.users && ` (filtered from ${dashboardData.users.length} total)`}
                                                </p>
                                                <div className="flex items-center gap-2">
                                                    <span className="text-sm text-muted-foreground">Show:</span>
                                                    <select
                                                        value={usersPerPage}
                                                        onChange={(e) => {
                                                            setUsersPerPage(parseInt(e.target.value, 10))
                                                            setCurrentPage(1)
                                                        }}
                                                        className="h-8 rounded-md border border-input bg-background px-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                                                    >
                                                        <option value={5}>5</option>
                                                        <option value={10}>10</option>
                                                        <option value={20}>20</option>
                                                    </select>
                                                </div>
                                            </div>
                                            {filteredUsers.length > usersPerPage && (
                                                <div className="flex items-center gap-1 sm:gap-2">
                                                    <Button
                                                        variant="outline"
                                                        size="sm"
                                                        onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                                                        disabled={currentPage === 1}
                                                    >
                                                        <ChevronLeft className="h-4 w-4" />
                                                        <span className="hidden sm:inline">Previous</span>
                                                    </Button>
                                                    <span className="text-sm text-muted-foreground px-1 sm:px-2">
                                                        {currentPage} / {Math.ceil(filteredUsers.length / usersPerPage)}
                                                    </span>
                                                    <Button
                                                        variant="outline"
                                                        size="sm"
                                                        onClick={() => setCurrentPage(p => Math.min(Math.ceil(filteredUsers.length / usersPerPage), p + 1))}
                                                        disabled={currentPage >= Math.ceil(filteredUsers.length / usersPerPage)}
                                                    >
                                                        <span className="hidden sm:inline">Next</span>
                                                        <ChevronRight className="h-4 w-4" />
                                                    </Button>
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </>
                            )
                        })()}
                    </CardContent>
                </Card>
            )}

            {/* User Form Dialog */}
            <UserFormDialog
                isOpen={showUserDialog}
                onClose={() => {
                    setShowUserDialog(false)
                    setSelectedUser(null)
                }}
                onSuccess={() => {
                    fetchDashboardData()
                    setShowUserDialog(false)
                    setSelectedUser(null)
                }}
                user={selectedUser}
                existingUsernames={(dashboardData?.users || []).map((u) => u.username)}
            />

            {/* Delete Confirmation Dialog */}
            <AlertDialog open={!!userToDelete} onOpenChange={() => userToDelete && setUserToDelete(null)}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Delete User</AlertDialogTitle>
                        <AlertDialogDescription>
                            Are you sure you want to delete this user? This action cannot be undone.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <div className="flex justify-end gap-3">
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={handleDeleteUser} className="bg-destructive">
                            Delete
                        </AlertDialogAction>
                    </div>
                </AlertDialogContent>
            </AlertDialog>

            {/* QR Code Dialog */}
            <Dialog open={showQrDialog} onOpenChange={setShowQrDialog}>
                <DialogContent className="sm:max-w-md">
                    <DialogHeader>
                        <DialogTitle>Subscription QR Code</DialogTitle>
                        <DialogDescription>
                            Scan this QR code.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="flex flex-col items-center space-y-4">
                        {qrUser && dashboardData?.sub_url && (
                            <>
                                <div className="p-4 bg-white rounded-lg border">
                                    <QRCodeSVG
                                        value={buildSubUrl(dashboardData.sub_url, qrUser.sub_id)}
                                        size={200}
                                        level="M"
                                    />
                                </div>
                                <div className="w-full space-y-2">
                                    <div className="text-sm text-muted-foreground text-center">
                                        <p><strong>User:</strong> {qrUser?.username}</p>
                                    </div>
                                    <div className="p-3 bg-muted rounded-md break-all text-xs font-mono">
                                        {buildSubUrl(dashboardData.sub_url, qrUser.sub_id)}
                                    </div>
                                </div>
                            </>
                        )}
                    </div>
                </DialogContent>
            </Dialog>
        </div >
    )
}

interface DetailsRowProps {
    user: ClientsOutput
    isExpanded: boolean
    subUrl?: string
    onToggle: () => void
    onEdit: () => void
    onDelete: () => void
    onResetUsage: () => void
    onShowQr: (user: ClientsOutput) => void
    onToggleStatus: () => void
}

function DetailsRow({
    user,
    isExpanded,
    subUrl,
    onToggle,
    onEdit,
    onDelete,
    onResetUsage,
    onShowQr,
    onToggleStatus,
}: DetailsRowProps) {
    const trafficUsed = user.used_data
    const trafficPercent = (trafficUsed / user.data_limit) * 100
    const online = lastOnlineInfo(user.online_at)

    return (
        <>
            <TableRow>
                <TableCell>
                    <button
                        onClick={onToggle}
                        className="p-1 hover:bg-muted rounded"
                    >
                        <ChevronDown
                            className={cn(
                                'h-4 w-4 transition-transform',
                                isExpanded && 'transform rotate-180'
                            )}
                        />
                    </button>
                </TableCell>
                <TableCell className="font-mono text-sm">{user.username}</TableCell>
                <TableCell>
                    <div className="space-y-1">
                        <div className="text-sm font-medium">
                            {bytesToGB(trafficUsed).toFixed(2)} / {bytesToGB(user.data_limit).toFixed(2)} GB
                        </div>
                        <div className="w-20 h-2 bg-muted rounded-full overflow-hidden">
                            <div
                                className={cn(
                                    'h-full bg-primary transition-all',
                                    trafficPercent > 80 && 'bg-destructive',
                                    trafficPercent > 90 && 'bg-destructive'
                                )}
                                style={{ width: `${Math.min(trafficPercent, 100)}%` }}
                            />
                        </div>
                    </div>
                </TableCell>
                <TableCell>
                    {user.expiry_date_unix ? (
                        <div className="space-y-1">
                            <div className="text-sm">{formatDate(user.expiry_date_unix)}</div>
                            <div className={cn(
                                'text-xs',
                                formatExpiryWithDays(user.expiry_date_unix).isExpired
                                    ? 'text-destructive'
                                    : formatExpiryWithDays(user.expiry_date_unix).daysLeft <= 7
                                        ? 'text-yellow-500'
                                        : 'text-muted-foreground'
                            )}>
                                {formatExpiryWithDays(user.expiry_date_unix).text}
                            </div>
                        </div>
                    ) : (
                        <span className="text-muted-foreground">No expiry</span>
                    )}
                </TableCell>
                <TableCell>
                    {online.online ? (
                        <Badge className="bg-emerald-500/15 text-emerald-500 border border-emerald-500/30">Online</Badge>
                    ) : (
                        <Badge variant={user.status ? 'default' : 'destructive'}>
                            {user.status ? 'Active' : 'Inactive'}
                        </Badge>
                    )}
                </TableCell>
                <TableCell className="text-right space-x-2">
                    <Button
                        size="sm"
                        variant="ghost"
                        onClick={onToggleStatus}
                        title={user.status ? 'Disable user' : 'Enable user'}
                    >
                        <Power className={cn("h-4 w-4", user.status ? "text-green-500" : "text-gray-400")} />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={onEdit}>
                        <Edit2 className="h-4 w-4" />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={onDelete}>
                        <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                </TableCell>
            </TableRow>

            {isExpanded && (
                <TableRow className="bg-muted/30">
                    <TableCell colSpan={6}>
                        <div className="py-4 space-y-3">
                            <div className="flex items-center gap-2 text-xs">
                                <Wifi className={cn('h-3.5 w-3.5', online.online ? 'text-emerald-500' : 'text-muted-foreground')} />
                                <span className="text-muted-foreground">Last online:</span>
                                <span>{online.text}</span>
                            </div>
                            {subUrl && user.sub_id && (
                                <div className="p-3 bg-background rounded-md border overflow-hidden">
                                    <div className="text-xs text-muted-foreground mb-1">Subscription Link:</div>
                                    <div className="text-xs font-mono break-all">{buildSubUrl(subUrl, user.sub_id)}</div>
                                </div>
                            )}
                            <div className="flex flex-wrap gap-2 pt-2">
                                <Button size="sm" variant="outline" onClick={onToggleStatus}>
                                    <Power className={cn("h-4 w-4 mr-2", user.status ? "text-green-500" : "text-gray-400")} />
                                    {user.status ? 'Disable' : 'Enable'}
                                </Button>
                                <Button size="sm" variant="outline" onClick={onResetUsage}>
                                    <RotateCcw className="h-4 w-4 mr-2" />
                                    Reset Usage
                                </Button>
                                {subUrl && user.sub_id && (
                                    <CopyButton
                                        text={buildSubUrl(subUrl, user.sub_id)}
                                        label="Copy Subscription"
                                        iconClassName="h-4 w-4 mr-2"
                                    />
                                )}
                                {subUrl && user.sub_id && (
                                    <Button
                                        size="sm"
                                        variant="outline"
                                        onClick={() => onShowQr(user)}
                                    >
                                        <QrCode className="h-4 w-4 mr-2" />
                                        QR Code
                                    </Button>
                                )}
                                <Button size="sm" variant="outline" onClick={onEdit}>
                                    <Edit2 className="h-4 w-4 mr-2" />
                                    Edit
                                </Button>
                                <Button size="sm" variant="destructive" onClick={onDelete}>
                                    <Trash2 className="h-4 w-4 mr-2" />
                                    Delete
                                </Button>
                            </div>
                        </div>
                    </TableCell>
                </TableRow>
            )}
        </>
    )
}

// Mobile User Card Component
interface MobileUserCardProps {
    user: ClientsOutput
    isExpanded: boolean
    subUrl?: string
    onToggle: () => void
    onEdit: () => void
    onDelete: () => void
    onResetUsage: () => void
    onShowQr: (user: ClientsOutput) => void
    onToggleStatus: () => void
}

function MobileUserCard({
    user,
    isExpanded,
    subUrl,
    onToggle,
    onEdit,
    onDelete,
    onResetUsage,
    onShowQr,
    onToggleStatus,
}: MobileUserCardProps) {
    const trafficUsed = user.used_data
    const trafficPercent = (trafficUsed / user.data_limit) * 100
    const online = lastOnlineInfo(user.online_at)

    return (
        <div className="border rounded-lg overflow-hidden">
            {/* Compact View - Always visible */}
            <button
                onClick={onToggle}
                className="w-full p-3 flex items-center gap-3 hover:bg-muted/50 transition-colors text-left"
            >
                {/* Left: Name & Traffic */}
                <div className="flex-1 min-w-0">
                    <span className="font-medium text-sm truncate block">{user.username}</span>
                    <div className="flex items-center gap-2 mt-1">
                        <span className="text-xs text-muted-foreground">
                            {bytesToGB(trafficUsed).toFixed(1)} / {bytesToGB(user.data_limit).toFixed(1)} GB
                        </span>
                        <div className="w-12 h-1.5 bg-muted rounded-full overflow-hidden">
                            <div
                                className={cn(
                                    'h-full bg-primary transition-all',
                                    trafficPercent > 80 && 'bg-destructive'
                                )}
                                style={{ width: `${Math.min(trafficPercent, 100)}%` }}
                            />
                        </div>
                    </div>
                </div>

                {/* Right: Status & Chevron */}
                <div className="flex flex-col items-end gap-1 shrink-0">
                    {online.online ? (
                        <Badge className="text-xs bg-emerald-500/15 text-emerald-500 border border-emerald-500/30">Online</Badge>
                    ) : (
                        <Badge variant={user.status ? 'default' : 'destructive'} className="text-xs">
                            {user.status ? 'Active' : 'Inactive'}
                        </Badge>
                    )}
                    <ChevronDown
                        className={cn(
                            'h-4 w-4 text-muted-foreground transition-transform',
                            isExpanded && 'transform rotate-180'
                        )}
                    />
                </div>
            </button>

            {/* Expanded View */}
            {isExpanded && (
                <div className="border-t p-3 space-y-3 bg-muted/30">
                    <div className="flex items-center gap-2 text-xs">
                        <Wifi className={cn('h-3.5 w-3.5', online.online ? 'text-emerald-500' : 'text-muted-foreground')} />
                        <span className="text-muted-foreground">Last online:</span>
                        <span>{online.text}</span>
                    </div>
                    {/* Subscription Link */}
                    {subUrl && user.sub_id && (
                        <div className="p-3 bg-background rounded-md border overflow-hidden">
                            <div className="text-xs text-muted-foreground mb-1">Subscription Link:</div>
                            <div className="text-xs font-mono break-all">{buildSubUrl(subUrl, user.sub_id)}</div>
                        </div>
                    )}

                    {/* Expiry */}
                    <div className="text-sm">
                        <p className="text-xs text-muted-foreground">Expiry Date</p>
                        {user.expiry_date_unix ? (
                            <div className="flex items-center gap-2">
                                <span className="font-medium">{formatDate(user.expiry_date_unix)}</span>
                                <span className={cn(
                                    'text-xs',
                                    formatExpiryWithDays(user.expiry_date_unix).isExpired
                                        ? 'text-destructive'
                                        : formatExpiryWithDays(user.expiry_date_unix).daysLeft <= 7
                                            ? 'text-yellow-500'
                                            : 'text-muted-foreground'
                                )}>
                                    ({formatExpiryWithDays(user.expiry_date_unix).text})
                                </span>
                            </div>
                        ) : (
                            <span className="text-muted-foreground">No expiry</span>
                        )}
                    </div>

                    {/* Action Buttons */}
                    <div className="flex flex-wrap gap-2 pt-1">
                        <Button
                            size="sm"
                            variant="outline"
                            className="flex-1 min-w-[80px]"
                            onClick={(e) => {
                                e.stopPropagation()
                                onToggleStatus()
                            }}
                        >
                            <Power className={cn("h-3 w-3 mr-1", user.status ? "text-green-500" : "text-gray-400")} />
                            {user.status ? 'Disable' : 'Enable'}
                        </Button>
                        <Button
                            size="sm"
                            variant="outline"
                            className="flex-1 min-w-[80px]"
                            onClick={(e) => {
                                e.stopPropagation()
                                onResetUsage()
                            }}
                        >
                            <RotateCcw className="h-3 w-3 mr-1" />
                            Reset
                        </Button>
                        {subUrl && user.sub_id && (
                            <CopyButton
                                text={buildSubUrl(subUrl, user.sub_id)}
                                label="Copy Sub"
                                iconClassName="h-3 w-3 mr-1"
                                className="flex-1 min-w-[80px]"
                                onClickCapture={(e) => e.stopPropagation()}
                            />
                        )}
                        {subUrl && user.sub_id && (
                            <Button
                                size="sm"
                                variant="outline"
                                className="flex-1 min-w-[80px]"
                                onClick={(e) => {
                                    e.stopPropagation()
                                    onShowQr(user)
                                }}
                            >
                                <QrCode className="h-3 w-3 mr-1" />
                                QR
                            </Button>
                        )}
                        <Button
                            size="sm"
                            variant="outline"
                            className="flex-1 min-w-[80px]"
                            onClick={(e) => {
                                e.stopPropagation()
                                onEdit()
                            }}
                        >
                            <Edit2 className="h-3 w-3 mr-1" />
                            Edit
                        </Button>
                        <Button
                            size="sm"
                            variant="destructive"
                            className="flex-1 min-w-[80px]"
                            onClick={(e) => {
                                e.stopPropagation()
                                onDelete()
                            }}
                        >
                            <Trash2 className="h-3 w-3 mr-1" />
                            Delete
                        </Button>
                    </div>
                </div>
            )}
        </div>
    )
}
