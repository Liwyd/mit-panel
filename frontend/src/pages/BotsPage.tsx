import { useEffect, useMemo, useState } from 'react'
import {
    Bot as BotIcon,
    LayoutDashboard,
    Package,
    Percent,
    CreditCard,
    Users,
    Layers,
    LayoutGrid,
    Type,
    Settings2,
    Smartphone,
    Megaphone,
    Server,
} from 'lucide-react'
import { botAPI, botsAPI, BotInfo, TelegramBot } from '@/lib/bots-api'
import { getUserRole } from '@/lib/auth'
import { cn } from '@/lib/utils'
import { BotName, ErrorBox, Loading, errorText, sameAsUsername } from './bots/common'
import { ManageBots } from './bots/ManageBots'
import { OverviewTab } from './bots/OverviewTab'
import { ProductsTab } from './bots/ProductsTab'
import { DiscountsTab } from './bots/DiscountsTab'
import { PaymentsTab } from './bots/PaymentsTab'
import { UsersTab } from './bots/UsersTab'
import { ServicesTab } from './bots/ServicesTab'
import { ButtonsTab } from './bots/ButtonsTab'
import { TextsTab } from './bots/TextsTab'
import { SettingsTab } from './bots/SettingsTab'
import { AutopayTab } from './bots/AutopayTab'
import { MessagesTab } from './bots/MessagesTab'
import { PanelsTab } from './bots/PanelsTab'
import { EmojiPacksCard } from './bots/EmojiPacksCard'
import { LockedBots } from './bots/Locked'

const TABS = [
    { key: 'overview', label: 'خلاصه', icon: LayoutDashboard },
    { key: 'products', label: 'محصولات', icon: Package },
    { key: 'payments', label: 'پرداخت‌ها', icon: CreditCard },
    { key: 'users', label: 'کاربران', icon: Users },
    { key: 'services', label: 'سرویس‌ها', icon: Layers },
    { key: 'discounts', label: 'تخفیف و هدیه', icon: Percent },
    { key: 'buttons', label: 'دکمه‌ها', icon: LayoutGrid },
    { key: 'texts', label: 'متن‌ها', icon: Type },
    { key: 'settings', label: 'تنظیمات', icon: Settings2 },
    { key: 'autopay', label: 'تأیید خودکار', icon: Smartphone },
    { key: 'messages', label: 'پیام و ادمین‌ها', icon: Megaphone },
    { key: 'panels', label: 'سرورها', icon: Server, superadmin: true },
] as const

type TabKey = (typeof TABS)[number]['key']

function stored(key: string): string | null {
    try {
        return localStorage.getItem(key)
    } catch {
        return null
    }
}
function store(key: string, value: string) {
    try {
        localStorage.setItem(key, value)
    } catch {
        /* private mode */
    }
}

export function BotsPage() {
    const superadmin = getUserRole() === 'superadmin'
    const [bots, setBots] = useState<TelegramBot[] | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [botId, setBotId] = useState<number | null>(() => Number(stored('nx-bot')) || null)
    const [tab, setTab] = useState<TabKey>(() => (stored('nx-bot-tab') as TabKey) || 'overview')
    // tagged with the bot it belongs to, so switching bots never shows stale info
    const [infoState, setInfoState] = useState<{ bot: number; info: BotInfo | null; error: string | null } | null>(null)

    const [reloads, setReloads] = useState(0)
    const load = () => setReloads((n) => n + 1)
    useEffect(() => {
        let live = true
        botsAPI
            .list()
            .then((list) => {
                if (!live) return
                setBots(list)
                setError(null)
                setBotId((cur) => (cur && list.some((b) => b.id === cur) ? cur : list[0]?.id ?? null))
            })
            .catch((err) => {
                if (!live) return
                setError(errorText(err))
                setBots([])
            })
        return () => {
            live = false
        }
    }, [reloads])

    const visibleBots = useMemo(() => (bots || []).filter((b) => superadmin || b.is_active), [bots, superadmin])
    const api = useMemo(() => (botId ? botAPI(botId) : null), [botId])
    const tabs = TABS.filter((t) => !('superadmin' in t) || superadmin)
    const activeTab: TabKey = tabs.some((t) => t.key === tab) ? tab : 'overview'

    useEffect(() => {
        if (!api || !botId) return
        store('nx-bot', String(botId))
        let live = true
        api.get<BotInfo>('info')
            .then((info) => live && setInfoState({ bot: botId, info, error: null }))
            .catch((err) => live && setInfoState({ bot: botId, info: null, error: errorText(err) }))
        return () => {
            live = false
        }
    }, [api, botId])
    const info = infoState?.bot === botId ? infoState.info : null
    const infoError = infoState?.bot === botId ? infoState.error : null

    if (bots === null) return <Loading />

    const current = visibleBots.find((b) => b.id === botId) || null

    return (
        <div dir="rtl" className="space-y-5 p-4 md:p-6 max-w-6xl">
            <div>
                <h1 className="text-2xl md:text-3xl font-bold tracking-tight flex items-center gap-2">
                    <BotIcon className="h-7 w-7 text-primary" /> ربات
                </h1>
                <p className="text-muted-foreground">مدیریت ربات فروش تلگرام: محصولات، پرداخت‌ها، کاربران، دکمه‌ها و تأیید خودکار.</p>
            </div>

            <ErrorBox error={error} />

            {superadmin && <ManageBots bots={bots} onChange={load} />}
            {superadmin && <EmojiPacksCard bots={bots} />}

            {!visibleBots.length ? (
                !superadmin && <LockedBots />
            ) : (
                <>
                    {visibleBots.length > 1 && (
                        <div className="flex flex-wrap gap-2">
                            {visibleBots.map((b) => (
                                <button
                                    key={b.id}
                                    onClick={() => setBotId(b.id)}
                                    className={cn(
                                        'rounded-full border px-4 py-1.5 text-sm transition',
                                        b.id === botId ? 'border-primary bg-primary text-primary-foreground' : 'border-border hover:bg-accent'
                                    )}
                                >
                                    <BotName name={b.name} username={b.bot_username} usernameClass="opacity-70 mr-1" />
                                </button>
                            ))}
                        </div>
                    )}

                    {current && (
                        <div className="flex flex-wrap items-center gap-2 text-sm">
                            {!sameAsUsername(current.name, current.bot_username) && (
                                <bdi dir="ltr" className="font-semibold">
                                    {current.name}
                                </bdi>
                            )}
                            {current.bot_username && (
                                <a className="text-primary hover:underline" dir="ltr" href={`https://t.me/${current.bot_username}`} target="_blank" rel="noopener noreferrer">
                                    @{current.bot_username}
                                </a>
                            )}
                            {info && <span className="text-xs text-muted-foreground">نسخه <span dir="ltr">{info.version}</span></span>}
                        </div>
                    )}
                    <ErrorBox error={infoError} />

                    <nav className="flex gap-1 overflow-x-auto pb-1 -mx-1 px-1">
                        {tabs.map((t) => {
                            const Icon = t.icon
                            return (
                                <button
                                    key={t.key}
                                    onClick={() => {
                                        setTab(t.key)
                                        store('nx-bot-tab', t.key)
                                    }}
                                    className={cn(
                                        'flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition',
                                        activeTab === t.key ? 'bg-primary text-primary-foreground' : 'hover:bg-accent text-muted-foreground'
                                    )}
                                >
                                    <Icon className="h-4 w-4" />
                                    {t.label}
                                </button>
                            )
                        })}
                    </nav>

                    {api && (
                        <div key={`${botId}-${activeTab}`}>
                            {activeTab === 'overview' && <OverviewTab api={api} info={info} />}
                            {activeTab === 'products' && <ProductsTab api={api} />}
                            {activeTab === 'payments' && <PaymentsTab api={api} />}
                            {activeTab === 'users' && <UsersTab api={api} />}
                            {activeTab === 'services' && <ServicesTab api={api} />}
                            {activeTab === 'discounts' && <DiscountsTab api={api} />}
                            {activeTab === 'buttons' && <ButtonsTab api={api} botKey={String(botId)} botName={current?.name || ''} />}
                            {activeTab === 'texts' && <TextsTab api={api} />}
                            {activeTab === 'settings' && <SettingsTab api={api} />}
                            {activeTab === 'autopay' && <AutopayTab api={api} superadmin={superadmin} />}
                            {activeTab === 'messages' && <MessagesTab api={api} />}
                            {activeTab === 'panels' && superadmin && <PanelsTab api={api} />}
                        </div>
                    )}
                </>
            )}
        </div>
    )
}
