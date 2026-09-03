import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
    BarChart3,
    Users,
    Settings,
    LogOut,
    Zap,
    HelpCircle,
    Sun,
    Moon,
    Server,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import { logout, getUserRole } from '@/lib/auth'
import { cn } from '@/lib/utils'
import { useTheme } from '@/hooks/useTheme'

interface SidebarProps {
    onItemClick?: () => void
}

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
    const [showFinanceInfo, setShowFinanceInfo] = useState(false)

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

                <Button
                    variant="ghost"
                    className="w-full justify-start gap-3"
                    onClick={() => setShowFinanceInfo(true)}
                >
                    <Zap className="h-4 w-4" />
                    <span>Finance</span>
                </Button>

                <Button
                    variant="ghost"
                    className="w-full justify-start gap-3 text-destructive hover:text-destructive"
                    onClick={handleLogout}
                >
                    <LogOut className="h-4 w-4" />
                    <span>Logout</span>
                </Button>
            </div>

            <Dialog open={showFinanceInfo} onOpenChange={setShowFinanceInfo}>
                <DialogContent className="sm:max-w-md">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <Zap className="h-5 w-5" />
                            Finance
                        </DialogTitle>
                        <DialogDescription className="pt-2 text-sm sm:text-base leading-7 sm:leading-8 text-foreground" dir="rtl">
                            برای شارژ پنل از ربات اختصاصی استفاده کنید.
                        </DialogDescription>
                    </DialogHeader>
                </DialogContent>
            </Dialog>
        </div>
    )
}
