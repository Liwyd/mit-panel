import { useLocation, useNavigate } from 'react-router-dom'
import {
    BarChart3,
    Users,
    Settings,
    LogOut,
    Zap,
    Sun,
    Moon,
    Server,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
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
                                'w-full justify-start gap-3',
                                isActive && 'bg-primary'
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
                    onClick={() => navigate('/login')}
                >
                    <Zap className="h-4 w-4" />
                    <span>Finance (Coming Soon)</span>
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
        </div>
    )
}
