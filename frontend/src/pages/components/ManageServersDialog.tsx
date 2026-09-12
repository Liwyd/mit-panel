import { useEffect, useState } from 'react'
import { Plus, Edit2, Trash2, Check, Copy, Loader2, AlertCircle, X, ChevronUp, ChevronDown } from 'lucide-react'
import { serverAPI } from '@/lib/api'
import { getApiClient } from '@/lib/api-client'
import { ServerOutput, ServerCreatedOutput } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
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

interface ManageServersDialogProps {
    isOpen: boolean
    onClose: () => void
    onChanged: () => void
}

function InstallSnippet({ server }: { server: ServerCreatedOutput }) {
    const [copied, setCopied] = useState(false)
    const panelUrl = getApiClient().defaults.baseURL || window.location.origin
    const command = `curl -fsSL https://raw.githubusercontent.com/liwyd/mit-panel/main/agent/install.sh | sudo bash -s -- --url "${panelUrl}" --token "${server.token}"`

    return (
        <div className="space-y-2 rounded-md border border-primary/30 bg-primary/5 p-3">
            <p className="text-sm font-semibold">
                "{server.name}" added. Run this on that server to start monitoring it:
            </p>
            <div className="flex items-start gap-2 rounded-md bg-background p-2 border">
                <code className="flex-1 break-all text-xs font-mono">{command}</code>
                <Button
                    size="xs"
                    variant="outline"
                    className="shrink-0"
                    onClick={() => {
                        navigator.clipboard.writeText(command)
                        setCopied(true)
                        setTimeout(() => setCopied(false), 1500)
                    }}
                >
                    {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                </Button>
            </div>
            <p className="text-xs text-muted-foreground">
                This token is shown only once. The row will show as "Connecting" until the agent's first check-in.
            </p>
        </div>
    )
}

export function ManageServersDialog({ isOpen, onClose, onChanged }: ManageServersDialogProps) {
    const [servers, setServers] = useState<ServerOutput[]>([])
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const [newName, setNewName] = useState('')
    const [adding, setAdding] = useState(false)
    const [justCreated, setJustCreated] = useState<ServerCreatedOutput | null>(null)

    const [renamingId, setRenamingId] = useState<number | null>(null)
    const [renameValue, setRenameValue] = useState('')
    const [savingRename, setSavingRename] = useState(false)

    const [deletingId, setDeletingId] = useState<number | null>(null)

    const load = async () => {
        try {
            setLoading(true)
            setServers(await serverAPI.getServers())
            setError(null)
        } catch (err: any) {
            setError(err?.message || 'Failed to fetch servers')
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        if (isOpen) {
            load()
            setJustCreated(null)
            setNewName('')
        }
    }, [isOpen])

    const handleAdd = async () => {
        if (!newName.trim()) return
        try {
            setAdding(true)
            setError(null)
            const created = await serverAPI.createServer(newName.trim())
            setJustCreated(created)
            setNewName('')
            await load()
            onChanged()
        } catch (err: any) {
            setError(err?.message || 'Failed to add server')
        } finally {
            setAdding(false)
        }
    }

    const startRename = (server: ServerOutput) => {
        setRenamingId(server.id)
        setRenameValue(server.name)
    }

    const handleRename = async (id: number) => {
        if (!renameValue.trim()) return
        try {
            setSavingRename(true)
            await serverAPI.renameServer(id, renameValue.trim())
            setRenamingId(null)
            await load()
            onChanged()
        } catch (err: any) {
            setError(err?.message || 'Failed to rename server')
        } finally {
            setSavingRename(false)
        }
    }

    const handleDelete = async () => {
        if (!deletingId) return
        try {
            await serverAPI.deleteServer(deletingId)
            setDeletingId(null)
            await load()
            onChanged()
        } catch (err: any) {
            setError(err?.message || 'Failed to remove server')
        }
    }

    const handleMove = async (index: number, direction: -1 | 1) => {
        const target = index + direction
        if (target < 0 || target >= servers.length) return

        const reordered = [...servers]
        const [moved] = reordered.splice(index, 1)
        reordered.splice(target, 0, moved)
        setServers(reordered)

        try {
            await serverAPI.reorderServers(reordered.map((s) => s.id))
            onChanged()
        } catch (err: any) {
            setError(err?.message || 'Failed to reorder servers')
            load()
        }
    }

    return (
        <>
            <Dialog open={isOpen} onOpenChange={onClose}>
                <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
                    <DialogHeader>
                        <DialogTitle>Manage Servers</DialogTitle>
                        <DialogDescription>
                            Add servers to monitor with the lightweight MIT Panel agent, or remove ones you no longer track.
                        </DialogDescription>
                    </DialogHeader>

                    {error && (
                        <div className="flex items-start gap-2 rounded-md bg-destructive/10 p-3 text-sm text-destructive border border-destructive/20">
                            <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                            <p>{error}</p>
                        </div>
                    )}

                    {justCreated && <InstallSnippet server={justCreated} />}

                    <div className="flex gap-2">
                        <Input
                            placeholder="Server name (e.g. Germany-1)"
                            value={newName}
                            onChange={(e) => setNewName(e.target.value)}
                            disabled={adding}
                            onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
                        />
                        <Button onClick={handleAdd} disabled={adding || !newName.trim()}>
                            {adding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                        </Button>
                    </div>

                    <div className="space-y-2">
                        {loading ? (
                            <p className="py-6 text-center text-sm text-muted-foreground">Loading...</p>
                        ) : servers.length === 0 ? (
                            <p className="py-6 text-center text-sm text-muted-foreground">No servers added yet</p>
                        ) : (
                            servers.map((server, index) => (
                                <div
                                    key={server.id}
                                    className="flex items-center gap-2 rounded-md border p-2"
                                >
                                    <div className="flex shrink-0 flex-col">
                                        <Button
                                            size="xs"
                                            variant="ghost"
                                            className="h-4 px-0.5"
                                            onClick={() => handleMove(index, -1)}
                                            disabled={index === 0}
                                        >
                                            <ChevronUp className="h-3.5 w-3.5" />
                                        </Button>
                                        <Button
                                            size="xs"
                                            variant="ghost"
                                            className="h-4 px-0.5"
                                            onClick={() => handleMove(index, 1)}
                                            disabled={index === servers.length - 1}
                                        >
                                            <ChevronDown className="h-3.5 w-3.5" />
                                        </Button>
                                    </div>
                                    {renamingId === server.id ? (
                                        <>
                                            <Input
                                                value={renameValue}
                                                onChange={(e) => setRenameValue(e.target.value)}
                                                disabled={savingRename}
                                                className="h-8"
                                                onKeyDown={(e) => e.key === 'Enter' && handleRename(server.id)}
                                                autoFocus
                                            />
                                            <Button
                                                size="sm"
                                                variant="ghost"
                                                onClick={() => handleRename(server.id)}
                                                disabled={savingRename}
                                            >
                                                <Check className="h-4 w-4 text-emerald-500" />
                                            </Button>
                                            <Button size="sm" variant="ghost" onClick={() => setRenamingId(null)}>
                                                <X className="h-4 w-4" />
                                            </Button>
                                        </>
                                    ) : (
                                        <>
                                            <span className="flex-1 min-w-0 truncate text-sm font-medium">
                                                {server.name}
                                            </span>
                                            <Button size="sm" variant="ghost" onClick={() => startRename(server)}>
                                                <Edit2 className="h-4 w-4" />
                                            </Button>
                                            <Button
                                                size="sm"
                                                variant="ghost"
                                                onClick={() => setDeletingId(server.id)}
                                            >
                                                <Trash2 className="h-4 w-4 text-destructive" />
                                            </Button>
                                        </>
                                    )}
                                </div>
                            ))
                        )}
                    </div>
                </DialogContent>
            </Dialog>

            <AlertDialog open={!!deletingId} onOpenChange={() => deletingId && setDeletingId(null)}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Stop monitoring this server?</AlertDialogTitle>
                        <AlertDialogDescription>
                            Its agent will keep running but the panel will stop tracking it. This can't be undone from here.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <div className="flex justify-end gap-3">
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={handleDelete} className="bg-destructive">
                            Remove
                        </AlertDialogAction>
                    </div>
                </AlertDialogContent>
            </AlertDialog>
        </>
    )
}
