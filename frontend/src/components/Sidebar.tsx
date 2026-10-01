import { useState, useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
    BarChart3,
    Users,
    Settings,
    LogOut,
    Zap,
    LifeBuoy,
    HelpCircle,
    Sun,
    Moon,
    Server,
} from 'lucide-react'
import { Button, buttonVariants } from '@/components/ui/button'
import { logout, getUserRole } from '@/lib/auth'
import { cn } from '@/lib/utils'
import { useTheme } from '@/hooks/useTheme'
import { settingsAPI } from '@/lib/api'

interface SidebarProps {
    onItemClick?: () => void
}

const TOPUP_BOT_URL = 'https://t.me/mitvpnpanelbot'
const SUPPORT_URL = 'https://t.me/MITsupports'

const navigationItems = [
    {
        label: 'Dashboard',
        href: '/',
        icon: BarChart3,
        roles: ['admin', 'superadmin'],
    },
    {
        label: 'Admins',
        href: '/admins',
        icon: Users,
        roles: ['superadmin'],
    },
    {
        label: 'Panels',
        href: '/panels',
        icon: Server,
        roles: ['superadmin'],
    },
    {
        label: 'Settings',
        href: '/settings',
        icon: Settings,
        roles: ['superadmin'],
    },
    {
        label: 'راهنما',
        href: '/help',
        icon: HelpCircle,
        roles: ['admin', 'superadmin'],
    },
]

function ThemeToggleButton() {
    const { theme, toggleTheme } = useTheme()

    return (
        <Button
            variant="ghost"
            className="w-full justify-start gap-3"
            onClick={toggleTheme}
        >
            {theme === 'light' ? (
                <Moon className="h-4 w-4" />
            ) : (
                <Sun className="h-4 w-4" />
            )}
            <span>{theme === 'light' ? 'Dark Mode' : 'Light Mode'}</span>
        </Button>
    )
}

export function Sidebar({ onItemClick }: SidebarProps) {
    const location = useLocation()
    const navigate = useNavigate()
    const userRole = getUserRole()
    const [version, setVersion] = useState('')

    useEffect(() => {
        settingsAPI.getVersion().then((data) => setVersion(data.version)).catch(() => {})
    }, [])

    const filteredItems = navigationItems.filter(item =>
        userRole && item.roles.includes(userRole)
    )

    const handleLogout = () => {
        logout()
    }

    return (
        <div className="flex flex-col h-full">
            <nav className="flex-1 space-y-2 p-4">
                {filteredItems.map((item) => {
                    const Icon = item.icon
                    const isActive = location.pathname === item.href

                    return (
                        <Button
                            key={item.href}
                            variant={isActive ? 'default' : 'ghost'}
                            className={cn(
                                'w-full justify-start gap-3 font-bold',
                                isActive && 'bg-primary shadow-none hover:translate-y-0'
                            )}
                            onClick={() => {
                                navigate(item.href)
                                onItemClick?.()
                            }}
                        >
                            <Icon className="h-4 w-4" />
                            <span>{item.label}</span>
                        </Button>
                    )
                })}
            </nav>

            <div className="border-t p-4 space-y-2">
                <ThemeToggleButton />

                {/* Straight to the bot rather than a dialog explaining there is
                    one — topping up is the only thing this ever led to. */}
                <a
                    href={TOPUP_BOT_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={onItemClick}
                    className={cn(buttonVariants({ variant: 'ghost' }), 'w-full justify-start gap-3')}
                >
                    <Zap className="h-4 w-4" />
                    <span>Finance</span>
                </a>

                <a
                    href={SUPPORT_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={onItemClick}
                    className={cn(buttonVariants({ variant: 'ghost' }), 'w-full justify-start gap-3')}
                >
                    <LifeBuoy className="h-4 w-4" />
                    <span>Support</span>
                </a>

                <Button
                    variant="ghost"
                    className="w-full justify-start gap-3 text-destructive hover:text-destructive"
                    onClick={handleLogout}
                >
                    <LogOut className="h-4 w-4" />
                    <span>Logout</span>
                </Button>

                {version && (
                    <div className="text-xs text-muted-foreground text-center pt-2 font-mono">
                        v{version}
                    </div>
                )}
            </div>
        </div>
    )
}
