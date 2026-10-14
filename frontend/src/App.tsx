import { useState } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { Sidebar } from '@/components/Sidebar'
import { LoginPage } from '@/pages/LoginPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { AdminsPage } from '@/pages/AdminsPage'
import { PanelsPage } from '@/pages/PanelsPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { HelpPage } from '@/pages/HelpPage'
import { BotsPage } from '@/pages/BotsPage'
import { Menu, X } from 'lucide-react'
import { Button } from '@/components/ui/button'

// BASE_URL carries a trailing slash ("/dashboard/"), and React Router only
// strips a basename when the URL starts with it in full — so a bare
// "/dashboard" matched nothing and rendered a blank page, while "/dashboard/"
// and "/dashboard/login" both worked. Without the slash both forms match.
const ROUTER_BASENAME = import.meta.env.BASE_URL.replace(/\/+$/, '') || '/'

function App() {
    return (
        <Router basename={ROUTER_BASENAME}>
            <Routes>
                {/* Public Routes */}
                <Route path="/login" element={<LoginPage />} />

                {/* Protected Routes */}
                <Route
                    path="/"
                    element={
                        <ProtectedRoute>
                            <Layout>
                                <DashboardPage />
                            </Layout>
                        </ProtectedRoute>
                    }
                />

                <Route
                    path="/admins"
                    element={
                        <ProtectedRoute>
                            <Layout>
                                <AdminsPage />
                            </Layout>
                        </ProtectedRoute>
                    }
                />

                <Route
                    path="/panels"
                    element={
                        <ProtectedRoute>
                            <Layout>
                                <PanelsPage />
                            </Layout>
                        </ProtectedRoute>
                    }
                />

                <Route
                    path="/bots"
                    element={
                        <ProtectedRoute>
                            <Layout>
                                <BotsPage />
                            </Layout>
                        </ProtectedRoute>
                    }
                />

                <Route
                    path="/settings"
                    element={
                        <ProtectedRoute>
                            <Layout>
                                <SettingsPage />
                            </Layout>
                        </ProtectedRoute>
                    }
                />

                <Route
                    path="/help"
                    element={
                        <ProtectedRoute>
                            <Layout>
                                <HelpPage />
                            </Layout>
                        </ProtectedRoute>
                    }
                />

                {/* Fallback */}
                <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
        </Router>
    )
}

function Layout({ children }: { children: React.ReactNode }) {
    const [sidebarOpen, setSidebarOpen] = useState(false)

    return (
        <div className="flex h-dvh w-screen bg-background overflow-hidden">
            {/* Mobile Sidebar Overlay */}
            {sidebarOpen && (
                <div
                    className="fixed inset-0 bg-black/50 z-40 md:hidden"
                    onClick={() => setSidebarOpen(false)}
                />
            )}

            {/* Mobile Sidebar */}
            <aside
                className={`fixed inset-y-0 left-0 z-50 flex w-64 flex-col bg-card border-r transform transition-transform duration-300 ease-in-out md:hidden ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'
                    }`}
            >
                <div className="flex items-center justify-between border-b px-4 pb-4 pt-[calc(env(safe-area-inset-top)_+_1rem)]">
                    <span className="font-black text-lg tracking-tight">MIT Panel</span>
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-11 w-11"
                        onClick={() => setSidebarOpen(false)}
                    >
                        <X className="h-5 w-5" />
                    </Button>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto pb-[env(safe-area-inset-bottom)]">
                    <Sidebar onItemClick={() => setSidebarOpen(false)} />
                </div>
            </aside>

            {/* Desktop Sidebar - Hidden on mobile */}
            <aside className="nx-header hidden md:flex w-64 border-r flex-col flex-shrink-0 h-dvh overflow-hidden">
                <div className="flex-1 overflow-y-auto">
                    <Sidebar />
                </div>
            </aside>

            {/* Main Content */}
            <div className="flex-1 flex flex-col min-w-0 h-dvh overflow-hidden">
                {/* Mobile Header with Menu Button. The band above (status bar /
                    notch) only exists in the installed app, and env() is 0 in a
                    plain browser tab, so this costs nothing there. */}
                <header className="nx-header md:hidden relative z-30 flex items-center gap-2 border-b px-4 pb-2 pt-[calc(env(safe-area-inset-top)_+_0.5rem)] shrink-0">
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-11 w-11"
                        onClick={() => setSidebarOpen(true)}
                    >
                        <Menu className="h-5 w-5" />
                    </Button>
                    <span className="font-black tracking-tight">MIT Panel</span>
                </header>

                <main className="flex-1 min-h-0 flex flex-col overflow-hidden">
                    {children}
                </main>
            </div>
        </div>
    )
}

export default App
