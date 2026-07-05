import { useEffect, useState } from 'react'
import {
    Download,
    Upload,
    FileText,
    Bell,
    Trash2,
    Database,
    RotateCcw,
    Eye,
    Plus,
    Image as ImageIcon,
    Send,
    Save,
    Loader2,
} from 'lucide-react'
import { superadminAPI, settingsAPI, getLogoUrl, type PanelSettings } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogHeader,
    AlertDialogTitle,
} from '@/components/ui/alert-dialog'

interface NewsItem {
    id: number
    message: string
    created_at: string
}

export function SettingsPage() {
    const [logs, setLogs] = useState<string[]>([])
    const [logsLoading, setLogsLoading] = useState(false)
    const [backupLoading, setBackupLoading] = useState(false)
    const [restoreLoading, setRestoreLoading] = useState(false)
    const [showLogsModal, setShowLogsModal] = useState(false)

    // News state
    const [news, setNews] = useState<NewsItem[]>([])
    const [newsLoading, setNewsLoading] = useState(false)
    const [newNewsMessage, setNewNewsMessage] = useState('')
    const [addingNews, setAddingNews] = useState(false)
    const [newsToDelete, setNewsToDelete] = useState<number | null>(null)
    const [deletingNews, setDeletingNews] = useState(false)
    const [showNewsDialog, setShowNewsDialog] = useState(false)
    const [showAddNewsDialog, setShowAddNewsDialog] = useState(false)

    // Settings (branding + telegram backup)
    const [settings, setSettings] = useState<PanelSettings | null>(null)
    const [savingSettings, setSavingSettings] = useState(false)
    const [uploadingLogo, setUploadingLogo] = useState(false)
    const [testingTelegram, setTestingTelegram] = useState(false)
    const [logoVersion, setLogoVersion] = useState(0)

    useEffect(() => {
        fetchNews()
        fetchSettings()
    }, [])

    const fetchSettings = async () => {
        try {
            const data = await settingsAPI.getSettings()
            setSettings(data)
        } catch (err: any) {
            console.error('Failed to fetch settings:', err)
        }
    }

    const handleSaveSettings = async () => {
        if (!settings) return
        try {
            setSavingSettings(true)
            const data = await settingsAPI.updateSettings({
                login_title: settings.login_title,
                telegram_bot_token: settings.telegram_bot_token,
                telegram_chat_id: settings.telegram_chat_id,
                backup_enabled: settings.backup_enabled,
                backup_interval_hours: Number(settings.backup_interval_hours) || 6,
            })
            setSettings(data)
            alert('Settings saved successfully')
        } catch (err: any) {
            alert(err?.message || 'Failed to save settings')
        } finally {
            setSavingSettings(false)
        }
    }

    const handleLogoUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0]
        if (!file) return
        try {
            setUploadingLogo(true)
            await settingsAPI.uploadLogo(file)
            setLogoVersion((v) => v + 1)
            await fetchSettings()
            alert('Logo updated successfully')
        } catch (err: any) {
            alert(err?.message || 'Failed to upload logo')
        } finally {
            setUploadingLogo(false)
            event.target.value = ''
        }
    }

    const handleTestTelegram = async () => {
        try {
            setTestingTelegram(true)
            const message = await settingsAPI.testTelegram()
            alert(message)
        } catch (err: any) {
            alert(err?.message || 'Failed to send test backup')
        } finally {
            setTestingTelegram(false)
        }
    }

    const fetchNews = async () => {
        try {
            setNewsLoading(true)
            const newsData = await superadminAPI.getNews()
            setNews(newsData)
        } catch (err: any) {
            console.error('Failed to fetch news:', err)
            alert(err?.message || 'Failed to fetch news')
        } finally {
            setNewsLoading(false)
        }
    }

    const fetchLogs = async () => {
        try {
            setLogsLoading(true)
            const logsData = await superadminAPI.getLogs()
            setLogs(logsData)
        } catch (err: any) {
            console.error('Failed to fetch logs:', err)
            alert(err?.message || 'Failed to fetch logs')
        } finally {
            setLogsLoading(false)
        }
    }

    const handleDownloadBackup = async () => {
        try {
            setBackupLoading(true)
            const blob = await superadminAPI.downloadBackup()
            const url = window.URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `backup-${new Date().toISOString().split('T')[0]}.db`
            document.body.appendChild(a)
            a.click()
            window.URL.revokeObjectURL(url)
            document.body.removeChild(a)
        } catch (err: any) {
            console.error('Failed to download backup:', err)
            alert(err?.message || 'Failed to download backup')
        } finally {
            setBackupLoading(false)
        }
    }

    const handleRestoreBackup = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0]
        if (!file) return

        try {
            setRestoreLoading(true)
            const message = await superadminAPI.restoreBackup(file)
            alert(message)
        } catch (err: any) {
            console.error('Failed to restore backup:', err)
            alert(err?.message || 'Failed to restore backup')
        } finally {
            setRestoreLoading(false)
            event.target.value = ''
        }
    }

    const handleAddNews = async () => {
        if (!newNewsMessage.trim()) {
            alert('Please enter a news message')
            return
        }

        try {
            setAddingNews(true)
            await superadminAPI.addNews(newNewsMessage)
            setNewNewsMessage('')
            fetchNews()
        } catch (err: any) {
            console.error('Failed to add news:', err)
            alert(err?.message || 'Failed to add news')
        } finally {
            setAddingNews(false)
        }
    }

    const handleDeleteNews = async () => {
        if (!newsToDelete) return

        try {
            setDeletingNews(true)
            await superadminAPI.deleteNews(newsToDelete)
            setNewsToDelete(null)
            fetchNews()
        } catch (err: any) {
            console.error('Failed to delete news:', err)
            alert(err?.message || 'Failed to delete news')
        } finally {
            setDeletingNews(false)
        }
    }

    return (
        <div className="space-y-6 p-4 md:p-6 max-w-full overflow-x-hidden">
            <div>
                <h1 className="text-2xl md:text-3xl font-semibold">Settings</h1>
                <p className="text-muted-foreground text-sm">Manage database, logs, and ...</p>
            </div>

            {/* 4 Main Boxes */}
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-2">
                {/* Backup Box */}
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Database className="h-5 w-5 text-blue-500" />
                            Database Backup
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p className="text-sm text-muted-foreground mb-4">
                            Download a backup of the current database.
                        </p>
                        <Button
                            onClick={handleDownloadBackup}
                            disabled={backupLoading}
                            className="w-full"
                        >
                            <Download className="mr-2 h-4 w-4" />
                            {backupLoading ? 'Downloading...' : 'Download Backup'}
                        </Button>
                    </CardContent>
                </Card>

                {/* Restore Box */}
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <RotateCcw className="h-5 w-5 text-amber-500" />
                            Database Restore
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p className="text-sm text-muted-foreground mb-4">
                            Restore database from a backup file.
                        </p>
                        <div className="space-y-2">
                            <Button
                                onClick={() => document.getElementById('restore-file-input')?.click()}
                                disabled={restoreLoading}
                                className="w-full"
                                variant="secondary"
                            >
                                <Upload className="mr-2 h-4 w-4" />
                                {restoreLoading ? 'Restoring...' : 'Select Backup File'}
                            </Button>
                            <Input
                                id="restore-file-input"
                                type="file"
                                accept=".db"
                                onChange={handleRestoreBackup}
                                disabled={restoreLoading}
                                className="hidden"
                            />
                        </div>
                    </CardContent>
                </Card>

                {/* Logs Box */}
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <FileText className="h-5 w-5 text-violet-500" />
                            Application Logs
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p className="text-sm text-muted-foreground mb-4">
                            View the latest application logs.
                        </p>
                        <Button
                            onClick={() => {
                                fetchLogs()
                                setShowLogsModal(true)
                            }}
                            disabled={logsLoading}
                            className="w-full"
                            variant="outline"
                        >
                            <Eye className="mr-2 h-4 w-4" />
                            {logsLoading ? 'Loading...' : 'Show Logs'}
                        </Button>
                    </CardContent>
                </Card>

                {/* News Box */}
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Bell className="h-5 w-5 text-rose-500" />
                            News Management
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                        <p className="text-sm text-muted-foreground">
                            Manage system news and announcements.
                        </p>
                        <div className="flex gap-2">
                            <Button
                                onClick={() => {
                                    fetchNews()
                                    setShowNewsDialog(true)
                                }}
                                disabled={newsLoading}
                                className="flex-1"
                                variant="outline"
                            >
                                <Eye className="mr-2 h-4 w-4" />
                                {newsLoading ? 'Loading...' : 'Show News'}
                            </Button>
                            <Button
                                onClick={() => setShowAddNewsDialog(true)}
                                className="flex-1"
                            >
                                <Plus className="mr-2 h-4 w-4" />
                                Create News
                            </Button>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Branding + Telegram Backup */}
            <div className="grid gap-6 md:grid-cols-2">
                {/* Branding */}
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <ImageIcon className="h-5 w-5 text-cyan-500" />
                            Login Branding
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="space-y-2">
                            <label className="text-sm font-medium">Login page title</label>
                            <Input
                                placeholder="MIT Panel"
                                value={settings?.login_title ?? ''}
                                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                                    settings && setSettings({ ...settings, login_title: e.target.value })
                                }
                                disabled={!settings}
                            />
                        </div>
                        <div className="space-y-2">
                            <label className="text-sm font-medium">Login logo</label>
                            <div className="flex items-center gap-3 flex-wrap">
                                {settings?.has_logo && (
                                    <img
                                        src={getLogoUrl(true) + '&v=' + logoVersion}
                                        alt="logo"
                                        className="h-12 w-auto rounded border bg-muted p-1"
                                    />
                                )}
                                <Button
                                    onClick={() => document.getElementById('logo-file-input')?.click()}
                                    disabled={uploadingLogo}
                                    variant="outline"
                                >
                                    <Upload className="mr-2 h-4 w-4" />
                                    {uploadingLogo ? 'Uploading...' : 'Upload Logo'}
                                </Button>
                                <Input
                                    id="logo-file-input"
                                    type="file"
                                    accept="image/*"
                                    onChange={handleLogoUpload}
                                    className="hidden"
                                />
                            </div>
                            <p className="text-xs text-muted-foreground">
                                PNG/JPG. Shown on the login page.
                            </p>
                        </div>
                    </CardContent>
                </Card>

                {/* Telegram Backup */}
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Send className="h-5 w-5 text-sky-500" />
                            Telegram Backup
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <label className="flex items-center gap-2 text-sm font-medium">
                            <input
                                type="checkbox"
                                className="h-4 w-4"
                                checked={!!settings?.backup_enabled}
                                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                                    settings && setSettings({ ...settings, backup_enabled: e.target.checked })
                                }
                            />
                            Enable automatic backup
                        </label>
                        <div className="space-y-2">
                            <label className="text-sm font-medium">Bot token</label>
                            <Input
                                placeholder="123456:ABC-DEF..."
                                value={settings?.telegram_bot_token ?? ''}
                                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                                    settings && setSettings({ ...settings, telegram_bot_token: e.target.value })
                                }
                            />
                        </div>
                        <div className="space-y-2">
                            <label className="text-sm font-medium">Chat ID (numeric)</label>
                            <Input
                                placeholder="123456789"
                                value={settings?.telegram_chat_id ?? ''}
                                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                                    settings && setSettings({ ...settings, telegram_chat_id: e.target.value })
                                }
                            />
                        </div>
                        <div className="space-y-2">
                            <label className="text-sm font-medium">Interval (hours)</label>
                            <Input
                                type="number"
                                min={1}
                                value={settings?.backup_interval_hours ?? 6}
                                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                                    settings && setSettings({ ...settings, backup_interval_hours: Number(e.target.value) })
                                }
                            />
                        </div>
                        <Button
                            onClick={handleTestTelegram}
                            disabled={testingTelegram}
                            variant="outline"
                            className="w-full"
                        >
                            <Send className="mr-2 h-4 w-4" />
                            {testingTelegram ? 'Sending...' : 'Send test backup now'}
                        </Button>
                    </CardContent>
                </Card>
            </div>

            <div className="flex justify-end">
                <Button
                    onClick={handleSaveSettings}
                    disabled={savingSettings || !settings}
                >
                    {savingSettings ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                        <Save className="mr-2 h-4 w-4" />
                    )}
                    {savingSettings ? 'Saving...' : 'Save Settings'}
                </Button>
            </div>

            {/* Logs Modal */}
            <Dialog open={showLogsModal} onOpenChange={setShowLogsModal}>
                <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle>Application Logs</DialogTitle>
                        <DialogDescription>
                            Latest 10 application logs
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-3">
                        <Button
                            onClick={fetchLogs}
                            disabled={logsLoading}
                            size="sm"
                            className="w-full"
                        >
                            <RotateCcw className="mr-2 h-4 w-4" />
                            {logsLoading ? 'Refreshing...' : 'Refresh Logs'}
                        </Button>
                        <div className="bg-muted p-4 rounded-xl max-h-96 overflow-y-auto border-2 border-foreground">
                            {logs.length > 0 ? (
                                <pre className="text-xs whitespace-pre-wrap font-mono">
                                    {logs.join('\n')}
                                </pre>
                            ) : (
                                <p className="text-sm text-muted-foreground">No logs available</p>
                            )}
                        </div>
                    </div>
                </DialogContent>
            </Dialog>

            {/* News Display Modal */}
            <Dialog open={showNewsDialog} onOpenChange={setShowNewsDialog}>
                <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle>Current News</DialogTitle>
                        <DialogDescription>
                            All system announcements
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-3">
                        {news.length > 0 ? (
                            <div className="space-y-2 max-h-96 overflow-y-auto">
                                {news.map((item) => (
                                    <div
                                        key={item.id}
                                        className="p-3 bg-muted rounded-xl border-2 border-foreground flex items-start justify-between gap-3"
                                    >
                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm break-words">{item.message}</p>
                                            <p className="text-xs text-muted-foreground mt-1">
                                                {new Date(item.created_at).toLocaleString()}
                                            </p>
                                        </div>
                                        <Button
                                            onClick={() => setNewsToDelete(item.id)}
                                            size="sm"
                                            variant="ghost"
                                            className="shrink-0 hover:bg-destructive/10">
                                            <Trash2 className="h-4 w-4 text-red-600" />
                                        </Button>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <p className="text-sm text-muted-foreground text-center py-4">
                                No news available
                            </p>
                        )}
                    </div>
                </DialogContent>
            </Dialog>

            {/* Add News Modal */}
            <Dialog open={showAddNewsDialog} onOpenChange={setShowAddNewsDialog}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Create News</DialogTitle>
                        <DialogDescription>
                            Add a new system announcement
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4">
                        <div>
                            <label className="text-sm font-medium">Message</label>
                            <Textarea
                                placeholder="Enter news message..."
                                value={newNewsMessage}
                                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setNewNewsMessage(e.target.value)}
                                className="mt-2 min-h-[100px]"
                                disabled={addingNews}
                            />
                        </div>
                        <div className="flex gap-2 justify-end">
                            <Button
                                onClick={() => {
                                    setShowAddNewsDialog(false)
                                    setNewNewsMessage('')
                                }}
                                variant="outline"
                                disabled={addingNews}
                            >
                                Cancel
                            </Button>
                            <Button
                                onClick={handleAddNews}
                                disabled={addingNews || !newNewsMessage.trim()}
                            >
                                <Plus className="mr-2 h-4 w-4" />
                                {addingNews ? 'Creating...' : 'Create News'}
                            </Button>
                        </div>
                    </div>
                </DialogContent>
            </Dialog>

            {/* Delete News Confirmation Dialog */}
            <AlertDialog open={!!newsToDelete} onOpenChange={() => newsToDelete && setNewsToDelete(null)}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Delete News</AlertDialogTitle>
                        <AlertDialogDescription>
                            Are you sure you want to delete this news? This action cannot be undone.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <div className="flex justify-end gap-3">
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction
                            onClick={handleDeleteNews}
                            disabled={deletingNews}
                            className="bg-destructive">
                            <Trash2 className="mr-2 h-4 w-4" />
                            {deletingNews ? 'Deleting...' : 'Delete'}
                        </AlertDialogAction>
                    </div>
                </AlertDialogContent>
            </AlertDialog >
        </div >
    )
}