import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import {
    Zap,
    Users,
    RefreshCw,
    ChevronLeft,
    ChevronRight,
    Plus,
    Edit2,
    RotateCcw,
    UserX,
    UserCog,
    Server,
    Clock,
    Wifi,
    Search,
} from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { dashboardAPI, userAPI, serverAPI } from '@/lib/api'
import { bytesToGB, formatTraffic } from '@/lib/traffic-converter'
import { formatDate, cn } from '@/lib/utils'
import { getUserRole, getUsername } from '@/lib/auth'
import { DashboardData, ClientsOutput, MeteredUsage, MarzbanOverview, MarzbanPeriod, MARZBAN_PERIODS, MarzbanNodeStatus, NewsFeedItem, ServerOutput } from '@/types'
import { useBannerImage } from '@/hooks/useBannerImage'
import { ManageServersDialog } from './components/ManageServersDialog'
import { UserList } from './components/UserList'
import { StatusFilter, type UserStatusFilter } from './components/StatusFilter'
import { buildSubUrl, lastOnlineInfo } from '@/lib/users'
import { Donut, Gauge, SEGMENT_COLORS } from '@/components/charts/Donut'
import { SegmentedBar } from '@/components/charts/SegmentedBar'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
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
import { PageLayout } from '@/components/PageLayout'
import { BlackFridayCountdown } from '@/components/BlackFridayCountdown'
import { DecorBoundary } from '@/components/DecorBoundary'

function NewsSlide({ item }: { item: NewsFeedItem }) {
    const bannerUrl = useBannerImage(item.id, item.has_banner)

    // Edge-to-edge: no card padding around the image, and a capped height
    // instead of a fixed aspect ratio — on a wide desktop viewport an
    // aspect-ratio box scaled to full width would tower over the dashboard.
    // Height grows per breakpoint and object-cover crops the width, so the
    // banner stays a sane size however wide the container is.
    if (item.has_banner) {
        return (
            <div className="w-full">
                {bannerUrl ? (
                    <img
                        src={bannerUrl}
                        alt={item.message || 'Announcement banner'}
                        className="h-36 w-full rounded-lg object-cover sm:h-44 md:h-52 lg:h-60"
                    />
                ) : (
                    <div className="flex h-36 w-full animate-pulse items-center justify-center rounded-lg bg-muted sm:h-44 md:h-52 lg:h-60">
                        <span className="text-xs text-muted-foreground">Loading...</span>
                    </div>
                )}
                {item.message && (
                    <p
                        className="px-6 pt-3 text-center text-sm font-medium leading-relaxed text-foreground"
                        style={{ direction: /[؀-ۿ]/.test(item.message) ? 'rtl' : 'ltr' }}
                    >
                        {item.message}
                    </p>
                )}
            </div>
        )
    }

    return (
        <div className="flex min-h-[160px] w-full items-center gap-2 px-6">
            <Zap className="h-5 w-5 flex-shrink-0 text-primary" />
            <div
                className="break-words text-base font-medium leading-relaxed text-foreground"
                style={{ direction: item.message && /[؀-ۿ]/.test(item.message) ? 'rtl' : 'ltr' }}
            >
                {item.message}
            </div>
        </div>
    )
}

function NewsCarousel({ items }: { items: NewsFeedItem[] }) {
    const [index, setIndex] = useState(0)

    // Derived rather than corrected in an effect: if the list shrinks while a
    // high index is selected, the modulo keeps the visible slide valid without
    // an extra render.
    const activeIndex = items.length > 0 ? index % items.length : 0

    useEffect(() => {
        if (items.length < 2) return
        const timer = setInterval(() => {
            setIndex((current) => (current + 1) % items.length)
        }, 6000)
        return () => clearInterval(timer)
    }, [items.length])

    const goTo = (i: number) => {
        if (!items.length) return
        setIndex(((i % items.length) + items.length) % items.length)
    }

    return (
        <div>
            <div className="overflow-hidden">
                <div
                    className="flex transition-transform duration-500 ease-out"
                    style={{ transform: `translateX(-${activeIndex * 100}%)` }}
                >
                    {items.map((item) => (
                        <div key={item.id} className="w-full flex-shrink-0">
                            <NewsSlide item={item} />
                        </div>
                    ))}
                </div>
            </div>

            {items.length > 1 && (
                <div className="flex items-center justify-center gap-3 pt-3">
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => goTo(activeIndex - 1)}>
                        <ChevronLeft className="h-4 w-4" />
                    </Button>
                    <div className="flex items-center gap-1.5">
                        {items.map((item, i) => (
                            <button
                                key={item.id}
                                type="button"
                                onClick={() => goTo(i)}
                                aria-label={`Go to slide ${i + 1}`}
                                className={cn(
                                    'h-1.5 rounded-full transition-[width,background-color,opacity] duration-200 ease-out',
                                    i === activeIndex ? 'w-5 bg-primary' : 'w-1.5 bg-muted-foreground/30'
                                )}
                            />
                        ))}
                    </div>
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => goTo(activeIndex + 1)}>
                        <ChevronRight className="h-4 w-4" />
                    </Button>
                </div>
            )}
        </div>
    )
}

const SERVER_STATUS_META: Record<string, { dot: string; label: string }> = {
    connected: { dot: 'bg-emerald-500', label: 'Connected' },
    connecting: { dot: 'bg-amber-500', label: 'Connecting' },
    disconnected: { dot: 'bg-destructive', label: 'Disconnected' },
}

// Marzban's own node enum, matching the Active/Inactive badge convention the
// rest of the dashboard uses rather than an unlabelled coloured dot.
const NODE_STATUS_BADGE: Record<
    MarzbanNodeStatus,
    { variant: 'secondary' | 'destructive' | 'outline' | 'success' | 'gold'; label: string }
> = {
    connected: { variant: 'success', label: 'Connected' },
    connecting: { variant: 'gold', label: 'Connecting' },
    error: { variant: 'destructive', label: 'Error' },
    disabled: { variant: 'outline', label: 'Disabled' },
    unknown: { variant: 'outline', label: 'Unknown' },
}

function ServerStatusDot({ status }: { status: string }) {
    const meta = SERVER_STATUS_META[status] || SERVER_STATUS_META.disconnected
    return (
        <span className="relative flex h-2.5 w-2.5 shrink-0" title={meta.label}>
            {status !== 'disconnected' && (
                <span className={cn('absolute inline-flex h-full w-full animate-ping rounded-full opacity-75', meta.dot)} />
            )}
            <span className={cn('relative inline-flex h-2.5 w-2.5 rounded-full', meta.dot)} />
        </span>
    )
}

// The last dashboard payload, in memory only (never written to storage: it
// holds subscription links). Keyed by the signed-in username so switching
// accounts never shows someone else's users.
let dashboardCache: { owner: string; data: DashboardData } | null = null

function readDashboardCache(): DashboardData | null {
    const owner = getUsername()
    return owner && dashboardCache?.owner === owner ? dashboardCache.data : null
}

function writeDashboardCache(data: DashboardData) {
    const owner = getUsername()
    dashboardCache = owner ? { owner, data } : null
}

export function DashboardPage() {
    // Coming back to the dashboard shows what was last loaded straight away and
    // refreshes underneath; the spinner is only for a first visit.
    const [dashboardData, setDashboardData] = useState<DashboardData | null>(() => readDashboardCache())
    const [loading, setLoading] = useState(() => readDashboardCache() === null)
    const [error, setError] = useState<string | null>(null)
    const [selectedUser, setSelectedUser] = useState<ClientsOutput | null>(null)
    const [showUserDialog, setShowUserDialog] = useState(false)
    const [userToDelete, setUserToDelete] = useState<string | null>(null)
    const [userToRevoke, setUserToRevoke] = useState<string | null>(null)
    const [revoking, setRevoking] = useState(false)
    const [showQrDialog, setShowQrDialog] = useState(false)
    const [qrUser, setQrUser] = useState<ClientsOutput | null>(null)
    const [currentPage, setCurrentPage] = useState(1)
    const [searchQuery, setSearchQuery] = useState('')
    const [statusFilter, setStatusFilter] = useState<UserStatusFilter>('all')
    const [marzban, setMarzban] = useState<MarzbanOverview | null>(null)
    const [marzbanPeriod, setMarzbanPeriod] = useState<MarzbanPeriod>('1d')
    const [marzbanAdminsLoaded, setMarzbanAdminsLoaded] = useState(false)
    const [statsRefreshing, setStatsRefreshing] = useState(false)
    const [servers, setServers] = useState<ServerOutput[]>([])
    const [showManageServers, setShowManageServers] = useState(false)
    const [serverToReboot, setServerToReboot] = useState<number | null>(null)
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
        const controller = new AbortController()

        // The online count comes from a scan the backend runs in the
        // background, so the first response normally carries null for it.
        let onlineLanded = false
        let inFlight = false

        const load = async () => {
            if (inFlight) return
            inFlight = true
            try {
                const includeAdmins = !marzbanAdminsLoaded
                const overview = await dashboardAPI.getMarzbanOverview(marzbanPeriod, false, includeAdmins)
                if (!cancelled && !controller.signal.aborted) {
                    setMarzban(overview)
                    if (typeof overview?.users.online === 'number') onlineLanded = true
                    if (includeAdmins && overview?.admins !== undefined) {
                        setMarzbanAdminsLoaded(true)
                    }
                }
            } catch (err) {
                if (!cancelled && !controller.signal.aborted) {
                    console.warn('Failed to fetch Marzban overview:', err)
                }
            } finally {
                inFlight = false
            }
        }

        load()
        const interval = setInterval(load, 30000)

        // Re-ask until that first count lands, instead of leaving the tile
        // empty for the rest of the poll cycle. Bounded so a scan that keeps
        // failing cannot settle into a request every few seconds forever.
        let attempts = 0
        const settle = setInterval(() => {
            if (onlineLanded || attempts >= 12) {
                clearInterval(settle)
                return
            }
            attempts += 1
            void load()
        }, 5000)

        return () => {
            cancelled = true
            controller.abort()
            clearInterval(interval)
            clearInterval(settle)
        }
    }, [userRole, marzbanPeriod, marzbanAdminsLoaded])

    // Auto-refresh system info every 15 seconds for superadmin
    useEffect(() => {
        if (userRole !== 'superadmin') return

        const controller = new AbortController()

        const interval = setInterval(async () => {
            try {
                const systemInfo = await dashboardAPI.getSystemInfo()
                if (!controller.signal.aborted) {
                    setDashboardData((prevData) =>
                        prevData ? { ...prevData, system: systemInfo } : null
                    )
                }
            } catch (err) {
                if (!controller.signal.aborted) {
                    console.warn('Failed to refresh system info:', err)
                }
            }
        }, 15000) // 15 seconds

        return () => {
            controller.abort()
            clearInterval(interval)
        }
    }, [userRole])

    // Monitored servers: the agent heartbeats every ~10s, so polling faster
    // than that would only ever return the same row again.
    const fetchServers = async () => {
        try {
            setServers(await serverAPI.getServers())
        } catch (err) {
            console.warn('Failed to fetch servers:', err)
        }
    }

    useEffect(() => {
        if (userRole !== 'superadmin') return

        const controller = new AbortController()

        fetchServers()
        const interval = setInterval(() => {
            if (!controller.signal.aborted) {
                fetchServers()
            }
        }, 30000) // 30 seconds
        return () => {
            controller.abort()
            clearInterval(interval)
        }
    }, [userRole])

    const handleRebootServer = async () => {
        if (!serverToReboot) return
        try {
            await serverAPI.rebootServer(serverToReboot)
            setServerToReboot(null)
            fetchServers()
        } catch (err: any) {
            console.error('Failed to queue reboot:', err)
            toast.error(err?.message || 'Failed to queue reboot')
        }
    }

    // Refreshes in place: after the first load the current list stays on screen
    // (scroll position and open rows included) until the new data replaces it.
    const fetchDashboardData = async () => {
        try {
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
            writeDashboardCache(data)
            setError(null)
        } catch (err: any) {
            console.error('Failed to fetch dashboard data:', err)
            setError(err?.message || 'Failed to fetch dashboard data')
        } finally {
            setLoading(false)
        }
    }

    // One button, both halves of the panel's own numbers: the overview and the
    // host system info sit on separate timers, so waiting for them means the
    // screen shows figures up to 15s old. `force` also clears the backend's
    // cached overview rather than serving it again.
    const handleRefreshStats = async () => {
        if (statsRefreshing) return
        setStatsRefreshing(true)
        try {
            const includeAdmins = !marzbanAdminsLoaded
            const [overview, systemInfo] = await Promise.all([
                dashboardAPI.getMarzbanOverview(marzbanPeriod, true, includeAdmins),
                userRole === 'superadmin'
                    ? dashboardAPI.getSystemInfo().catch(() => null)
                    : Promise.resolve(null),
            ])
            setMarzban(overview)
            if (includeAdmins && overview?.admins !== undefined) {
                setMarzbanAdminsLoaded(true)
            }
            if (systemInfo) {
                setDashboardData((prev) => (prev ? { ...prev, system: systemInfo } : prev))
            }
        } catch (err) {
            console.warn('Failed to refresh stats:', err)
        } finally {
            setStatsRefreshing(false)
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
            toast.error(err?.message || 'Failed to delete user')
        }
    }

    const handleResetUsage = async (email: string) => {
        try {
            await userAPI.resetUserUsage(email)
            fetchDashboardData()
        } catch (err: any) {
            console.error('Failed to reset usage:', err)
            toast.error(err?.message || 'Failed to reset usage')
        }
    }

    const handleRevoke = async () => {
        if (!userToRevoke || revoking) return
        setRevoking(true)
        try {
            const subscriptionUrl = await userAPI.revokeSubscription(userToRevoke)
            setDashboardData((previous) => previous ? {
                ...previous,
                users: previous.users?.map((user) => user.username === userToRevoke ? { ...user, sub_id: subscriptionUrl } : user),
            } : previous)
            setUserToRevoke(null)
            await fetchDashboardData()
        } catch (err: unknown) {
            toast.error(err instanceof Error ? err.message : 'Could not confirm revocation; refresh before retrying')
        } finally {
            setRevoking(false)
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
            toast.error(err?.message || 'Failed to toggle user status')
        }
    }

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-full">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
            </div>
        )
    }

    // Search first, then sort each match into its status; the filter shows how
    // many of the current search results fall into every status.
    const query = searchQuery.toLowerCase()
    const statusCounts: Record<UserStatusFilter, number> = { all: 0, online: 0, active: 0, inactive: 0 }
    const filteredUsers = (dashboardData?.users ?? []).filter(user => {
        const matchesSearch = user.username.toLowerCase().includes(query) ||
            (user.uuid && user.uuid.toLowerCase().includes(query))
        if (!matchesSearch) return false
        const online = lastOnlineInfo(user.online_at).online
        statusCounts.all++
        if (online) statusCounts.online++
        if (user.status && !online) statusCounts.active++
        if (!user.status) statusCounts.inactive++
        if (statusFilter === 'all') return true
        if (statusFilter === 'online') return online
        if (statusFilter === 'active') return user.status && !online
        if (statusFilter === 'inactive') return !user.status
        return true
    })

    return (
        <PageLayout
            header={
                <div className="p-4 md:p-6 pb-0">
                    {/* Page Title */}
                    <div>
                        <h1 className="text-2xl md:text-3xl font-bold tracking-tight">Dashboard</h1>
                        <p className="text-muted-foreground">Welcome back!</p>
                    </div>
                </div>
            }
            footer={
                dashboardData?.users && filteredUsers.length > 0
                    ? (
                        <div className="p-4 md:p-6 pt-0">
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
                        </div>
                    )
                    : undefined
            }
        >
            <div className="space-y-6 p-4 md:p-6 max-w-full overflow-x-hidden">
            {/* Black Friday countdown, only while the theme is on */}
            <DecorBoundary>
                <BlackFridayCountdown />
            </DecorBoundary>

            {/* Error Message */}
            {error && (
                <div className="rounded-md bg-destructive/10 p-4 text-sm text-destructive border border-destructive/20">
                    {error}
                </div>
            )}

            {/* Marzban Overview - superadmin only */}
            {userRole === 'superadmin' && marzban && (
                <div className="space-y-4">
                    {/* Which Marzban this data came from, and a way to stop
                        waiting for the next silent poll. */}
                    <div className="flex flex-wrap items-center justify-between gap-3">
                        <h2 className="text-lg font-black leading-tight">
                            {marzban.panel}
                            {marzban.version && (
                                <span className="ml-2 text-sm font-bold text-muted-foreground">
                                    v{marzban.version}
                                </span>
                            )}
                        </h2>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={handleRefreshStats}
                            disabled={statsRefreshing}
                        >
                            <RefreshCw
                                className={cn('h-4 w-4', statsRefreshing && 'animate-spin')}
                            />
                            <span>Refresh</span>
                        </Button>
                    </div>

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
                                        {marzban.users.online === null ? (
                                            <span className="text-muted-foreground">…</span>
                                        ) : (
                                            marzban.users.online.toLocaleString()
                                        )}
                                    </p>
                                    <p className="text-xs text-muted-foreground">
                                        {marzban.users.online === null ? 'Counting…' : 'Across all nodes'}
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
                                            const badge =
                                                NODE_STATUS_BADGE[node.status] ??
                                                NODE_STATUS_BADGE.unknown
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
                                                    <Badge variant={badge.variant} className="shrink-0">
                                                        {badge.label}
                                                    </Badge>
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
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
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

                    {/* Marzban admins with no MIT Panel account. They can serve
                        users nobody in this panel knows about, so a non-zero
                        count is worth a look. Fetched once on load, then kept
                        across the silent overview polls. */}
                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-medium">MIT vs Marzban Admins</CardTitle>
                            <UserCog className="h-4 w-4 text-amber-500" />
                        </CardHeader>
                        <CardContent className="flex items-center gap-4">
                            <Donut
                                size={72}
                                thickness={10}
                                segments={[
                                    { label: 'MIT Panel', value: marzban?.admins?.mit ?? 0, color: 'hsl(var(--brand-blue))' },
                                    {
                                        label: 'Marzban only',
                                        value: marzban?.admins?.marzban_only ?? 0,
                                        color: 'hsl(var(--muted-foreground) / 0.25)',
                                    },
                                ]}
                            />
                            <div className="min-w-0">
                                <div className="text-2xl font-bold tabular leading-tight">
                                    {marzban?.admins ? (
                                        <>
                                            {marzban.admins.mit.toLocaleString()}
                                            <span className="text-base font-bold text-muted-foreground">
                                                {' / '}{marzban.admins.marzban_only.toLocaleString()}
                                            </span>
                                        </>
                                    ) : (
                                        <span className="text-muted-foreground">—</span>
                                    )}
                                </div>
                                <p className="text-xs text-muted-foreground">
                                    {marzban?.admins
                                        ? 'MIT Panel / Marzban-only'
                                        : 'Requires an active Marzban panel'}
                                </p>
                            </div>
                        </CardContent>
                    </Card>
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

            {/* Servers - monitored via the lightweight MIT Panel agent */}
            {userRole === 'superadmin' && (
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-base">Servers</CardTitle>
                        <div className="flex items-center gap-1">
                            <Button size="sm" variant="ghost" onClick={fetchServers} title="Refresh">
                                <RefreshCw className="h-4 w-4" />
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => setShowManageServers(true)} title="Manage servers">
                                <Edit2 className="h-4 w-4" />
                            </Button>
                        </div>
                    </CardHeader>
                    <CardContent>
                        {servers.length === 0 ? (
                            <p className="py-6 text-center text-sm text-muted-foreground">
                                No servers added yet. Use the pencil icon above to add one.
                            </p>
                        ) : (
                            <div className="divide-y">
                                {servers.map((server) => {
                                    const ramPercent = server.ram_total ? ((server.ram_used || 0) / server.ram_total) * 100 : null
                                    const swapPercent = server.swap_total ? ((server.swap_used || 0) / server.swap_total) * 100 : null
                                    const diskPercent = server.disk_total ? ((server.disk_used || 0) / server.disk_total) * 100 : null
                                    const hasMetrics = server.status !== 'disconnected' || server.last_seen_at

                                    return (
                                        <div
                                            key={server.id}
                                            className="flex flex-wrap items-center gap-x-6 gap-y-2 py-3"
                                        >
                                            <div className="flex w-full shrink-0 items-center gap-2 sm:w-36">
                                                <ServerStatusDot status={server.status} />
                                                <span className="truncate text-sm font-bold">{server.name}</span>
                                            </div>

                                            {hasMetrics && server.cpu_percent !== null && server.cpu_percent !== undefined ? (
                                                <div className="grid min-w-[240px] flex-1 grid-cols-2 gap-x-5 gap-y-3 xl:grid-cols-4">
                                                    <SegmentedBar
                                                        percent={server.cpu_percent}
                                                        label="CPU"
                                                        caption={server.cpu_cores ? `${server.cpu_cores} cores` : undefined}
                                                    />
                                                    <SegmentedBar
                                                        percent={ramPercent ?? 0}
                                                        label="RAM"
                                                        caption={
                                                            server.ram_used !== undefined && server.ram_used !== null
                                                                ? `${bytesToGB(server.ram_used).toFixed(1)}/${bytesToGB(server.ram_total || 0).toFixed(1)} GB`
                                                                : undefined
                                                        }
                                                    />
                                                    <SegmentedBar
                                                        percent={swapPercent ?? 0}
                                                        label="Swap"
                                                        caption={
                                                            server.swap_total
                                                                ? `${bytesToGB(server.swap_used || 0).toFixed(1)}/${bytesToGB(server.swap_total || 0).toFixed(1)} GB`
                                                                : 'None'
                                                        }
                                                    />
                                                    <SegmentedBar
                                                        percent={diskPercent ?? 0}
                                                        label="Storage"
                                                        caption={
                                                            server.disk_used !== undefined && server.disk_used !== null
                                                                ? `${bytesToGB(server.disk_used).toFixed(1)}/${bytesToGB(server.disk_total || 0).toFixed(1)} GB`
                                                                : undefined
                                                        }
                                                    />
                                                </div>
                                            ) : (
                                                <span className="text-xs text-muted-foreground">
                                                    {server.status === 'connecting' ? 'Waiting for first check-in...' : 'No data'}
                                                </span>
                                            )}

                                            <Button
                                                size="sm"
                                                variant="outline"
                                                className="ml-auto"
                                                onClick={() => setServerToReboot(server.id)}
                                            >
                                                <RotateCcw className="h-4 w-4 mr-2" />
                                                Reboot
                                            </Button>
                                        </div>
                                    )
                                })}
                            </div>
                        )}
                    </CardContent>
                </Card>
            )}

            {/* Admin News - Only for admin role. No Card wrapper on purpose:
                a banner image is meant to be the whole visual, not a picture
                inside another frame - so there's nothing here but the
                carousel itself. */}
            {userRole === 'admin' && dashboardData?.news && dashboardData.news.length > 0 && (
                <NewsCarousel items={dashboardData.news} />
            )}



            {/* Admin Stats Row - Only for admin role */}
            {userRole === 'admin' && dashboardData && (
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                    {dashboardData.metered ? (
                        <MeteredUsageCard usage={dashboardData.metered} />
                    ) : (
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
                    )}

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
                        <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
                            <StatusFilter
                                value={statusFilter}
                                counts={statusCounts}
                                onChange={(value) => {
                                    setStatusFilter(value)
                                    setCurrentPage(1)
                                }}
                            />
                            <div className="relative flex-1">
                                <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                                <Input
                                    type="text"
                                    placeholder="Search users by email or username..."
                                    value={searchQuery}
                                    onChange={(e) => {
                                        setSearchQuery(e.target.value)
                                        setCurrentPage(1)
                                    }}
                                    className="h-10 rounded-xl border-border/70 bg-muted/30 pl-10 focus-visible:bg-card"
                                />
                            </div>
                        </div>
                    </CardHeader>

                    <CardContent>
                        {(() => {
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
                                <UserList
                                    users={paginatedUsers}
                                    subUrl={dashboardData.sub_url}
                                    onEdit={(user) => {
                                        setSelectedUser(user)
                                        setShowUserDialog(true)
                                    }}
                                    onDelete={(user) => setUserToDelete(`${user.uuid || '0'}|${user.username}|${user.id}`)}
                                    onResetUsage={(user) => handleResetUsage(user.username)}
                                    onRevoke={dashboardData.can_revoke_subscription ? (user) => setUserToRevoke(user.username) : undefined}
                                    onShowQr={(user) => {
                                        setQrUser(user)
                                        setShowQrDialog(true)
                                    }}
                                    onToggleStatus={(user) => handleToggleStatus(user)}
                                />
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
            <AlertDialog open={!!userToRevoke} onOpenChange={(open) => { if (!open && !revoking) setUserToRevoke(null) }}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Revoke subscription for {userToRevoke}?</AlertDialogTitle>
                        <AlertDialogDescription>Current proxy credentials will stop working. The user must update their configuration.</AlertDialogDescription>
                    </AlertDialogHeader>
                    <div className="flex justify-end gap-3">
                        <AlertDialogCancel disabled={revoking}>Cancel</AlertDialogCancel>
                        <Button variant="destructive" disabled={revoking} onClick={handleRevoke}>{revoking ? 'Revoking...' : 'Revoke Subscription'}</Button>
                    </div>
                </AlertDialogContent>
            </AlertDialog>
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

            {/* Manage Servers Dialog */}
            <ManageServersDialog
                isOpen={showManageServers}
                onClose={() => setShowManageServers(false)}
                onChanged={fetchServers}
            />

            {/* Reboot Server Confirmation */}
            <AlertDialog open={!!serverToReboot} onOpenChange={() => serverToReboot && setServerToReboot(null)}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Reboot this server?</AlertDialogTitle>
                        <AlertDialogDescription>
                            It will restart as soon as its agent picks up the request, usually within a few seconds. Any active connections on it will drop.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <div className="flex justify-end gap-3">
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={handleRebootServer} className="bg-destructive">
                            Reboot
                        </AlertDialogAction>
                    </div>
                </AlertDialogContent>
            </AlertDialog>
        </div>
        </PageLayout>
    )
}

/** Usage-billed («ادمین ویژه») admins see what they used, not a balance. */
function MeteredUsageCard({ usage }: { usage: MeteredUsage }) {
    const since = usage.since ? new Date(usage.since).toLocaleDateString() : null
    const readAt = usage.read_at
        ? new Date(usage.read_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        : null
    return (
        <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Traffic Used</CardTitle>
                <Zap className="h-4 w-4 text-primary" />
            </CardHeader>
            <CardContent>
                <div className="text-2xl font-bold">{bytesToGB(usage.used_bytes).toFixed(2)} GB</div>
                <p className="text-xs text-muted-foreground">
                    {since ? `Since ${since}` : 'Usage-billed'} · this week {bytesToGB(usage.unsettled_bytes).toFixed(2)} GB
                </p>
                {usage.prepaid_bytes > 0 && (
                    <p className="text-xs text-muted-foreground">
                        Prepaid left: {bytesToGB(usage.prepaid_bytes).toFixed(2)} GB
                    </p>
                )}
                {readAt && <p className="text-xs text-muted-foreground">Updated {readAt}</p>}
            </CardContent>
        </Card>
    )
}
