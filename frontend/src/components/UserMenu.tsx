import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronDown, LogOut, Settings } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { getUsername, logout } from '@/lib/auth'

export function UserMenu() {
    const navigate = useNavigate()
    const username = getUsername()
    const [isOpen, setIsOpen] = useState(false)

    const handleLogout = () => {
        logout()
    }

    return (
        <DropdownMenu open={isOpen} onOpenChange={setIsOpen}>
            <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="gap-2">
                    <div className="w-9 h-9 rounded-full bg-primary border-2 border-foreground shadow-neo-sm flex items-center justify-center text-white text-sm font-bold">
                        {username?.charAt(0).toUpperCase() || 'U'}
                    </div>
                    <span className="hidden sm:inline text-sm font-bold uppercase tracking-wider">{username}</span>
                    <ChevronDown className="h-4 w-4" />
                </Button>
            </DropdownMenuTrigger>

            <DropdownMenuContent align="end" className="w-48">
                <div className="px-3 py-2 text-sm font-bold uppercase tracking-wider">{username}</div>
                <DropdownMenuSeparator />

                <DropdownMenuItem
                    onClick={() => {
                        navigate('/settings')
                        setIsOpen(false)
                    }}
                    className="gap-2"
                >
                    <Settings className="h-4 w-4" />
                    <span>Settings</span>
                </DropdownMenuItem>

                <DropdownMenuSeparator />

                <DropdownMenuItem
                    onClick={handleLogout}
                    className="gap-2 text-destructive focus:text-destructive"
                >
                    <LogOut className="h-4 w-4" />
                    <span>Logout</span>
                </DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
    )
}
