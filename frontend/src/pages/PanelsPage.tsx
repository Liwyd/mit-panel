import { useEffect, useState } from 'react'
import {
    ChevronDown,
    Plus,
    Edit2,
    Trash2,
    ToggleLeft,
    ToggleRight,
    Copy,
} from 'lucide-react'
import { panelAPI, dashboardAPI } from '@/lib/api'
import { cn } from '@/lib/utils'
import { PanelOutput } from '@/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogHeader,
    AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { PanelFormDialog } from './components/PanelFormDialog'

interface ExpandedRow {
    [key: string]: boolean
}

export function PanelsPage() {
    const [panels, setPanels] = useState<PanelOutput[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [expandedRows, setExpandedRows] = useState<ExpandedRow>({})
    const [selectedPanel, setSelectedPanel] = useState<PanelOutput | null>(null)
    const [showPanelDialog, setShowPanelDialog] = useState(false)
    const [panelToDelete, setPanelToDelete] = useState<number | null>(null)

    useEffect(() => {
        fetchPanels()
    }, [])

    const fetchPanels = async () => {
        try {
            setLoading(true)
            const data = await dashboardAPI.getPanels()
            setPanels(data)
            setError(null)
        } catch (err: any) {
            console.error('Failed to fetch panels:', err)
            setError(err?.message || 'Failed to fetch panels')
        } finally {
            setLoading(false)
        }
    }

    const handleDeletePanel = async () => {
        if (!panelToDelete) return

        try {
            await panelAPI.deletePanel(panelToDelete)
            setPanelToDelete(null)
            fetchPanels()
        } catch (err: any) {
            console.error('Failed to delete panel:', err)
            alert(err?.message || 'Failed to delete panel')
        }
    }

    const handleToggleStatus = async (panelId: number) => {
        try {
            await panelAPI.togglePanelStatus(panelId)
            fetchPanels()
        } catch (err: any) {
            console.error('Failed to toggle panel status:', err)
            alert(err?.message || 'Failed to toggle panel status')
        }
    }

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
            </div>
        )
    }

    return (
        <div className="space-y-6 p-4 md:p-6 max-w-full overflow-x-hidden">
            {/* Page Title */}
            <div>
                <h1 className="text-2xl md:text-3xl font-bold tracking-tight">Panels Management</h1>
                <p className="text-muted-foreground">Manage your proxy panels</p>
            </div>

            {/* Error Message */}
            {error && (
                <div className="rounded-md bg-destructive/10 p-4 text-sm text-destructive border border-destructive/20">
                    {error}
                </div>
            )}

            {/* Panels Table */}
            <Card>
                <CardHeader className="flex flex-row items-center justify-between">
                    <div>
                        <CardTitle>Panels</CardTitle>
                        <CardDescription>
                            {panels.length} panel{panels.length !== 1 ? 's' : ''} total
                        </CardDescription>
                    </div>
                    <Button
                        size="sm"
                        onClick={() => {
                            setSelectedPanel(null)
                            setShowPanelDialog(true)
                        }}
                    >
                        <Plus className="h-4 w-4 mr-2" />
                        Add Panel
                    </Button>
                </CardHeader>

                <CardContent>
                    {panels.length === 0 ? (
                        <div className="text-center py-8">
                            <p className="text-muted-foreground">No panels configured yet</p>
                        </div>
                    ) : (
                        <>
                            {/* Mobile View - Cards */}
                            <div className="md:hidden space-y-3">
                                {panels.map((panel) => (
                                    <MobilePanelCard
                                        key={panel.id}
                                        panel={panel}
                                        isExpanded={expandedRows[panel.id.toString()] || false}
                                        onToggle={() => {
                                            setExpandedRows(prev => ({
                                                ...prev,
                                                [panel.id.toString()]: !prev[panel.id.toString()],
                                            }))
                                        }}
                                        onEdit={() => {
                                            setSelectedPanel(panel)
                                            setShowPanelDialog(true)
                                        }}
                                        onDelete={() => setPanelToDelete(panel.id)}
                                        onToggleStatus={() => handleToggleStatus(panel.id)}
                                    />
                                ))}
                            </div>

                            {/* Desktop View - Table */}
                            <div className="hidden md:block overflow-x-auto">
                                <Table>
                                    <TableHeader>
                                        <TableRow>
                                            <TableHead className="w-12"></TableHead>
                                            <TableHead>Name</TableHead>
                                            <TableHead>Type</TableHead>
                                            <TableHead>URL</TableHead>
                                            <TableHead>Status</TableHead>
                                            <TableHead className="text-right">Actions</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {panels.map((panel) => (
                                            <PanelDetailsRow
                                                key={panel.id}
                                                panel={panel}
                                                isExpanded={expandedRows[panel.id.toString()] || false}
                                                onToggle={() => {
                                                    setExpandedRows(prev => ({
                                                        ...prev,
                                                        [panel.id.toString()]: !prev[panel.id.toString()],
                                                    }))
                                                }}
                                                onEdit={() => {
                                                    setSelectedPanel(panel)
                                                    setShowPanelDialog(true)
                                                }}
                                                onDelete={() => setPanelToDelete(panel.id)}
                                                onToggleStatus={() => handleToggleStatus(panel.id)}
                                            />
                                        ))}
                                    </TableBody>
                                </Table>
                            </div>
                        </>
                    )}
                </CardContent>
            </Card>

            {/* Panel Form Dialog */}
            <PanelFormDialog
                isOpen={showPanelDialog}
                onClose={() => {
                    setShowPanelDialog(false)
                    setSelectedPanel(null)
                }}
                onSuccess={() => {
                    fetchPanels()
                    setShowPanelDialog(false)
                    setSelectedPanel(null)
                }}
                panel={selectedPanel}
            />

            {/* Delete Confirmation Dialog */}
            <AlertDialog open={!!panelToDelete} onOpenChange={() => panelToDelete && setPanelToDelete(null)}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Delete Panel</AlertDialogTitle>
                        <AlertDialogDescription>
                            Are you sure you want to delete this panel? This action cannot be undone.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <div className="flex justify-end gap-3">
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={handleDeletePanel} className="bg-destructive">
                            Delete
                        </AlertDialogAction>
                    </div>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    )
}

interface PanelDetailsRowProps {
    panel: PanelOutput
    isExpanded: boolean
    onToggle: () => void
    onEdit: () => void
    onDelete: () => void
    onToggleStatus: () => void
}

function PanelDetailsRow({
    panel,
    isExpanded,
    onToggle,
    onEdit,
    onDelete,
    onToggleStatus,
}: PanelDetailsRowProps) {
    return (
        <>
            <TableRow>
                <TableCell>
                    <button
                        onClick={onToggle}
                        className="p-1 hover:bg-muted rounded"
                    >
                        <ChevronDown
                            className={cn(
                                'h-4 w-4 transition-transform',
                                isExpanded && 'transform rotate-180'
                            )}
                        />
                    </button>
                </TableCell>
                <TableCell className="font-semibold">{panel.name}</TableCell>
                <TableCell>
                    <Badge variant="outline">{panel.panel_type}</Badge>
                </TableCell>
                <TableCell className="max-w-xs truncate text-sm font-mono">
                    {panel.url}
                </TableCell>
                <TableCell>
                    <Badge variant={panel.is_active ? 'default' : 'destructive'}>
                        {panel.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                </TableCell>
                <TableCell className="text-right space-x-2">
                    <Button size="sm" variant="ghost" onClick={onToggleStatus}>
                        {panel.is_active ? (
                            <ToggleRight className="h-4 w-4 text-green-600" />
                        ) : (
                            <ToggleLeft className="h-4 w-4 text-muted-foreground" />
                        )}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={onEdit}>
                        <Edit2 className="h-4 w-4" />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={onDelete}>
                        <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                </TableCell>
            </TableRow>

            {isExpanded && (
                <TableRow className="bg-muted/30">
                    <TableCell colSpan={6}>
                        <div className="py-4 space-y-3">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                                <div>
                                    <p className="text-muted-foreground">Panel URL</p>
                                    <p className="font-mono break-all text-xs">{panel.url}</p>
                                    <Button
                                        size="xs"
                                        variant="outline"
                                        className="mt-2"
                                        onClick={() => navigator.clipboard.writeText(panel.url)}
                                    >
                                        <Copy className="h-3 w-3 mr-1" />
                                        Copy
                                    </Button>
                                </div>
                            </div>
                        </div>
                    </TableCell>
                </TableRow>
            )}
        </>
    )
}

// Mobile Panel Card Component
function MobilePanelCard({
    panel,
    isExpanded,
    onToggle,
    onEdit,
    onDelete,
    onToggleStatus,
}: PanelDetailsRowProps) {
    return (
        <div className="border rounded-lg overflow-hidden">
            {/* Compact View */}
            <button
                onClick={onToggle}
                className="w-full p-3 flex items-center gap-3 hover:bg-muted/50 transition-colors text-left"
            >
                <div className="flex-1 min-w-0">
                    <span className="font-medium text-sm truncate block">{panel.name}</span>
                    <div className="flex items-center gap-2 mt-1">
                        <Badge variant="outline" className="text-xs">{panel.panel_type}</Badge>
                    </div>
                </div>

                <div className="flex flex-col items-end gap-1 shrink-0">
                    <Badge variant={panel.is_active ? 'default' : 'destructive'} className="text-xs">
                        {panel.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                    <ChevronDown
                        className={cn(
                            'h-4 w-4 text-muted-foreground transition-transform',
                            isExpanded && 'transform rotate-180'
                        )}
                    />
                </div>
            </button>

            {/* Expanded View */}
            {isExpanded && (
                <div className="border-t p-3 space-y-3 bg-muted/30">
                    <div className="text-sm">
                        <p className="text-xs text-muted-foreground">Panel URL</p>
                        <p className="font-mono text-xs break-all mt-1">{panel.url}</p>
                        <Button
                            size="sm"
                            variant="outline"
                            className="mt-2"
                            onClick={(e) => {
                                e.stopPropagation()
                                navigator.clipboard.writeText(panel.url)
                            }}
                        >
                            <Copy className="h-3 w-3 mr-1" />
                            Copy URL
                        </Button>
                    </div>

                    <div className="flex flex-wrap gap-2 pt-1">
                        <Button
                            size="sm"
                            variant="outline"
                            className="flex-1 min-w-[70px]"
                            onClick={(e) => {
                                e.stopPropagation()
                                onToggleStatus()
                            }}
                        >
                            {panel.is_active ? (
                                <ToggleRight className="h-3 w-3 mr-1 text-green-600" />
                            ) : (
                                <ToggleLeft className="h-3 w-3 mr-1" />
                            )}
                            {panel.is_active ? 'Disable' : 'Enable'}
                        </Button>
                        <Button
                            size="sm"
                            variant="outline"
                            className="flex-1 min-w-[70px]"
                            onClick={(e) => {
                                e.stopPropagation()
                                onEdit()
                            }}
                        >
                            <Edit2 className="h-3 w-3 mr-1" />
                            Edit
                        </Button>
                        <Button
                            size="sm"
                            variant="destructive"
                            className="flex-1 min-w-[70px]"
                            onClick={(e) => {
                                e.stopPropagation()
                                onDelete()
                            }}
                        >
                            <Trash2 className="h-3 w-3 mr-1" />
                            Delete
                        </Button>
                    </div>
                </div>
            )}
        </div>
    )
}
