import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Menu, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ThemeToggle } from './ThemeToggle'
import { UserMenu } from './UserMenu'
import { Sidebar } from './Sidebar'

export function Header() {
    const [sidebarOpen, setSidebarOpen] = useState(false)

    return (
        <>
            <header className="nx-header border-b sticky top-0 z-40">
                <div className="flex items-center justify-between h-16 px-4 md:px-6">
                    <div className="flex items-center gap-4">
                        <Button
                            variant="ghost"
                            size="icon"
                            className="md:hidden"
                            onClick={() => setSidebarOpen(!sidebarOpen)}
                        >
                            {sidebarOpen ? (
                                <X className="h-5 w-5" />
                            ) : (
                                <Menu className="h-5 w-5" />
                            )}
                        </Button>

                        <Link to="/dashboard" className="flex items-center gap-2 font-black text-lg tracking-tight">
                            <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center text-white">
                                W
                            </div>
                            <span className="hidden sm:inline"></span>
                        </Link>
                    </div>

                    <div className="flex items-center gap-2">
                        <ThemeToggle />
                        <UserMenu />
                    </div>
                </div>
            </header>

            {/* Mobile Sidebar */}
            {sidebarOpen && (
                <div className="fixed inset-0 z-30 md:hidden bg-background/80 backdrop-blur-sm">
                    <div className="fixed left-0 top-16 h-[calc(100vh-4rem)] w-64 bg-background border-r">
                        <Sidebar onItemClick={() => setSidebarOpen(false)} />
                    </div>
                    <div
                        className="absolute inset-0"
                        onClick={() => setSidebarOpen(false)}
                    />
                </div>
            )}
        </>
    )
}
