import { useState } from 'react'
import { ClipboardCheck, LayoutDashboard, Settings2, Type, Zap } from 'lucide-react'
import { topupBotAPI } from '@/lib/bots-api'
import { cn } from '@/lib/utils'
import { PageLayout } from '@/components/PageLayout'
import { TopupOverview } from './topup/TopupOverview'
import { TopupSettings } from './topup/TopupSettings'
import { TopupTexts } from './topup/TopupTexts'
import { TopupRequests } from './topup/TopupRequests'

const TABS = [
    { key: 'overview', label: 'خلاصه', icon: LayoutDashboard },
    { key: 'settings', label: 'تنظیمات', icon: Settings2 },
    { key: 'texts', label: 'متن‌ها', icon: Type },
    { key: 'requests', label: 'رسیدها', icon: ClipboardCheck },
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

export function TopupBotPage() {
    const [tab, setTab] = useState<TabKey>(stored)
    const choose = (t: TabKey) => {
        setTab(t)
        try {
            localStorage.setItem('nx-topup-tab', t)
        } catch {
            /* private mode */
        }
    }

    const header = (
        <div className="space-y-4 p-4 md:p-6 pb-2 border-b border-border bg-background">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <h1 className="text-2xl md:text-3xl font-bold tracking-tight flex items-center gap-2">
                        <Zap className="h-7 w-7 text-primary" /> ربات تاپ‌آپ
                    </h1>
                    <p className="text-muted-foreground text-sm">مدیریت زنده‌ی ربات شارژ: وضعیت، رسیدها، تنظیمات مالی و متن پیام‌ها.</p>
                </div>
            </div>
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
        </div>
    )

    return (
        <PageLayout header={header}>
            <div dir="rtl" className="p-4 md:p-6 max-w-6xl">
                <div key={tab}>
                    {tab === 'overview' && <TopupOverview api={topupBotAPI} />}
                    {tab === 'settings' && <TopupSettings api={topupBotAPI} />}
                    {tab === 'texts' && <TopupTexts api={topupBotAPI} />}
                    {tab === 'requests' && <TopupRequests api={topupBotAPI} />}
                </div>
            </div>
        </PageLayout>
    )
}
