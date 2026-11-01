import { useState } from 'react'
import { LayoutDashboard, LayoutGrid, Plug, Settings2, Type, Zap } from 'lucide-react'
import { TopupConnection, topupBotAPI, topupConnectionAPI } from '@/lib/bots-api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBox, Field, Loading, Notice, Spinner, useAction, useLoad } from './bots/common'
import { TopupOverview } from './topup/TopupOverview'
import { TopupSettings } from './topup/TopupSettings'
import { TopupTexts } from './topup/TopupTexts'
import { TopupButtons } from './topup/TopupButtons'

const TABS = [
    { key: 'overview', label: 'خلاصه', icon: LayoutDashboard },
    { key: 'settings', label: 'تنظیمات', icon: Settings2 },
    { key: 'texts', label: 'متن‌ها', icon: Type },
    { key: 'buttons', label: 'دکمه‌ها', icon: LayoutGrid },
] as const

type TabKey = (typeof TABS)[number]['key']

function stored(): TabKey {
    try {
        const v = localStorage.getItem('nx-topup-tab')
        return TABS.some((t) => t.key === v) ? (v as TabKey) : 'overview'
    } catch {
        return 'overview'
    }
}

// The reseller top-up bot, run from the panel (superadmin only). The panel
// forwards to the bot's management API; see backend/api/topup_bot/routers.py.
export function TopupBotPage() {
    const conn = useLoad(() => topupConnectionAPI.get(), [])
    const [tab, setTab] = useState<TabKey>(stored)
    const choose = (t: TabKey) => {
        setTab(t)
        try {
            localStorage.setItem('nx-topup-tab', t)
        } catch {
            /* private mode */
        }
    }

    return (
        <div dir="rtl" className="space-y-5 p-4 md:p-6 max-w-6xl">
            <div>
                <h1 className="text-2xl md:text-3xl font-bold tracking-tight flex items-center gap-2">
                    <Zap className="h-7 w-7 text-primary" /> ربات تاپ‌آپ
                </h1>
                <p className="text-muted-foreground">مدیریت ربات شارژ پنل نماینده‌ها: تنظیمات، متن پیام‌ها و دکمه‌ها، رنگ دکمه‌ها و ایموجی پریمیوم.</p>
            </div>

            {conn.loading && !conn.data ? (
                <Loading />
            ) : (
                <ConnectionCard conn={conn.data} error={conn.error} onSaved={conn.setData} />
            )}

            {conn.data?.connected && (
                <>
                    <nav className="flex gap-1 overflow-x-auto pb-1 -mx-1 px-1">
                        {TABS.map((t) => {
                            const Icon = t.icon
                            return (
                                <button
                                    key={t.key}
                                    onClick={() => choose(t.key)}
                                    className={cn(
                                        'flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition',
                                        tab === t.key ? 'bg-primary text-primary-foreground' : 'hover:bg-accent text-muted-foreground'
                                    )}
                                >
                                    <Icon className="h-4 w-4" />
                                    {t.label}
                                </button>
                            )
                        })}
                    </nav>
                    <div key={tab}>
                        {tab === 'overview' && <TopupOverview api={topupBotAPI} />}
                        {tab === 'settings' && <TopupSettings api={topupBotAPI} />}
                        {tab === 'texts' && <TopupTexts api={topupBotAPI} />}
                        {tab === 'buttons' && <TopupButtons api={topupBotAPI} />}
                    </div>
                </>
            )}
        </div>
    )
}

function ConnectionCard({
    conn,
    error,
    onSaved,
}: {
    conn: TopupConnection | null
    error: string | null
    onSaved: (c: TopupConnection) => void
}) {
    const [editing, setEditing] = useState(!conn?.url)
    const [url, setUrl] = useState(conn?.url || '')
    const [key, setKey] = useState('')
    const act = useAction()

    if (conn?.connected && !editing) {
        return (
            <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card p-3 text-sm">
                <span className="h-2 w-2 rounded-full bg-brand-green" />
                <span>متصل به</span>
                {conn.bot_username ? (
                    <a className="text-primary hover:underline" dir="ltr" href={`https://t.me/${conn.bot_username}`} target="_blank" rel="noopener noreferrer">
                        @{conn.bot_username}
                    </a>
                ) : (
                    <bdi dir="ltr">{conn.url}</bdi>
                )}
                <Button size="sm" variant="ghost" className="mr-auto" onClick={() => setEditing(true)}>
                    <Plug className="h-4 w-4 ml-1" /> تغییر اتصال
                </Button>
            </div>
        )
    }

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <Plug className="h-5 w-5" /> اتصال به ربات تاپ‌آپ
                </CardTitle>
                <CardDescription className="leading-6">
                    آدرس API مدیریت ربات را وارد کنید؛ پورت پیش‌فرض ۸۰۹۰ است (مثلاً <bdi dir="ltr">http://172.17.0.1:8090</bdi> وقتی پنل و ربات روی یک سرور هستند،
                    یا <bdi dir="ltr">http://IP-سرور-ربات:8090</bdi>). کلید پیش‌فرض همان <bdi dir="ltr">BOT_API_KEY</bdi> پنل است که ربات هم دارد؛ فقط اگر در ربات
                    <bdi dir="ltr"> MANAGEMENT_API_KEY</bdi> جداگانه گذاشته‌اید آن را اینجا بنویسید.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
                <ErrorBox error={conn?.error || error} />
                <Field label="آدرس ربات">
                    <Input dir="ltr" value={url} placeholder="http://172.17.0.1:8090" onChange={(e) => setUrl(e.target.value)} />
                </Field>
                <Field label="کلید (اختیاری)" hint={conn?.own_key ? 'یک کلید جداگانه ذخیره شده است؛ خالی بگذارید تا همان بماند.' : undefined}>
                    <Input dir="ltr" type="password" value={key} onChange={(e) => setKey(e.target.value)} />
                </Field>
                <ErrorBox error={act.error} />
                <Notice text={act.notice} />
                <div className="flex gap-2">
                    <Button
                        disabled={act.busy || !url.trim()}
                        onClick={async () => {
                            const res = await act.run(() => topupConnectionAPI.set(url, key), 'متصل شد')
                            if (res && res !== true) {
                                onSaved(res as TopupConnection)
                                setKey('')
                                setEditing(false)
                            }
                        }}
                    >
                        {act.busy && <Spinner className="ml-2" />} اتصال
                    </Button>
                    {conn?.connected && (
                        <Button variant="outline" onClick={() => setEditing(false)}>
                            انصراف
                        </Button>
                    )}
                </div>
            </CardContent>
        </Card>
    )
}
