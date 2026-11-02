import { useCallback, useEffect, useMemo, useState } from 'react'
import { Check, Pencil, Save, Trash2 } from 'lucide-react'
import { adminAPI, dashboardAPI } from '@/lib/api'
import { AdminGroupAssignment, InboundGroup, PanelOutput } from '@/types'
import { PageLayout } from '@/components/PageLayout'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { AlertCircle } from 'lucide-react'

function messageFromError(error: unknown, fallback: string): string {
    return error instanceof Error ? error.message : fallback
}

export function InboundGroupsPage() {
    const [panels, setPanels] = useState<PanelOutput[]>([])
    const [panel, setPanel] = useState('')
    const [inbounds, setInbounds] = useState<Record<string, string[]>>({})
    const [groups, setGroups] = useState<InboundGroup[]>([])
    const [admins, setAdmins] = useState<AdminGroupAssignment[]>([])
    const [name, setName] = useState('')
    const [selected, setSelected] = useState<Record<string, string[]>>({})
    const [editing, setEditing] = useState<number | null>(null)
    const [isDefault, setIsDefault] = useState(false)
    const [assignments, setAssignments] = useState<Record<number, { ids: number[]; defaultId: number | null }>>({})
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState('')
    const [notice, setNotice] = useState('')

    const marzbanPanels = useMemo(() => panels.filter((p) => p.panel_type === 'marzban'), [panels])

    const refresh = useCallback(async (selectedPanel = panel) => {
        if (!selectedPanel) return
        const [nextGroups, nextInbounds, nextAdmins] = await Promise.all([
            adminAPI.listInboundGroups(selectedPanel),
            adminAPI.getPanelInbounds(selectedPanel),
            adminAPI.listAdminGroupAssignments(),
        ])
        setGroups(nextGroups)
        setInbounds(nextInbounds)
        setAdmins(nextAdmins.filter((a) => a.panel === selectedPanel))
        setAssignments((old) => {
            const next = { ...old }
            nextAdmins.filter((a) => a.panel === selectedPanel).forEach((a) => {
                next[a.id] = { ids: a.assigned_group_ids, defaultId: a.default_group_id }
            })
            return next
        })
    }, [panel])

    useEffect(() => {
        dashboardAPI.getPanels().then((items) => {
            const eligible = items.filter((p) => p.panel_type === 'marzban')
            setPanels(eligible)
            if (eligible[0]) setPanel(eligible[0].name)
        }).catch((e) => setError(e.message || 'Failed to load panels'))
    }, [])

    useEffect(() => {
        if (panel) refresh(panel).catch((e) => setError(e.message || 'Failed to load inbound groups'))
    }, [panel, refresh])

    const toggle = (protocol: string, tag: string) => {
        setSelected((old) => {
            const tags = old[protocol] || []
            const nextTags = tags.includes(tag) ? tags.filter((item) => item !== tag) : [...tags, tag]
            return { ...old, [protocol]: nextTags }
        })
    }

    const resetEditor = () => {
        setEditing(null)
        setName('')
        setSelected({})
        setIsDefault(false)
    }

    const edit = (group: InboundGroup) => {
        setEditing(group.id)
        setName(group.name)
        setSelected(group.inbounds)
        setIsDefault(group.is_default)
    }

    const save = async () => {
        setBusy(true)
        setError('')
        setNotice('')
        try {
            const inboundsToSave = isDefault ? inbounds : Object.fromEntries(
                Object.entries(selected).filter(([, tags]) => tags.length > 0),
            )
            await adminAPI.saveInboundGroup({ panel, name: isDefault ? (name.trim() || 'Default (all inbounds)') : name.trim(), inbounds: inboundsToSave, is_default: isDefault }, editing ?? undefined)
            resetEditor()
            await refresh()
            setNotice('Inbound group saved.')
        } catch (e: unknown) {
            setError(messageFromError(e, 'Failed to save inbound group'))
        } finally {
            setBusy(false)
        }
    }

    const remove = async (group: InboundGroup) => {
        if (!window.confirm(`Delete “${group.name}”? Assigned admins will have this group unassigned.`)) return
        try {
            await adminAPI.deleteInboundGroup(group.id)
            await refresh()
            setNotice('Inbound group deleted.')
        } catch (e: unknown) {
            setError(messageFromError(e, 'Failed to delete inbound group'))
        }
    }

    const toggleAdminGroup = (adminId: number, groupId: number) => {
        setAssignments((old) => {
            const current = old[adminId] || { ids: [], defaultId: null }
            const ids = current.ids.includes(groupId) ? current.ids.filter((id) => id !== groupId) : [...current.ids, groupId]
            return { ...old, [adminId]: { ids, defaultId: ids.includes(current.defaultId || -1) ? current.defaultId : null } }
        })
    }

    const saveAssignment = async (admin: AdminGroupAssignment) => {
        const value = assignments[admin.id] || { ids: [], defaultId: null }
        try {
            await adminAPI.setAdminGroups(admin.id, value.ids, value.defaultId)
            setNotice(`Groups assigned to ${admin.username}.`)
        } catch (e: unknown) {
            setError(messageFromError(e, 'Failed to assign groups'))
        }
    }

    return (
        <PageLayout header={<div className="p-6"><h1 className="text-2xl font-bold">Inbound Groups</h1><p className="text-sm text-muted-foreground">Create reusable Marzban inbound combinations and assign them to reseller admins.</p></div>}>
            <div className="space-y-6 p-6 pt-0">
                {error && <div className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"><AlertCircle className="h-4 w-4" />{error}</div>}
                {notice && <div className="rounded-md border border-primary/30 bg-primary/5 p-3 text-sm">{notice}</div>}
                <div className="max-w-xl space-y-2"><Label>Marzban panel</Label><Select value={panel} onValueChange={setPanel}><SelectTrigger><SelectValue placeholder="Select panel" /></SelectTrigger><SelectContent>{marzbanPanels.map((item) => <SelectItem key={item.name} value={item.name}>{item.name}</SelectItem>)}</SelectContent></Select></div>

                <div className="grid gap-6 xl:grid-cols-2">
                    <Card><CardHeader><CardTitle>{editing ? 'Edit inbound group' : 'Create inbound group'}</CardTitle><CardDescription>The default group always uses the panel’s current full inbound set.</CardDescription></CardHeader><CardContent className="space-y-4">
                        <div className="space-y-2"><Label>Group name</Label><Input value={name} maxLength={80} onChange={(e) => setName(e.target.value)} placeholder="e.g. Premium routes" /></div>
                        <label className="flex cursor-pointer items-center gap-2 text-sm"><input type="checkbox" checked={isDefault} onChange={(e) => setIsDefault(e.target.checked)} /> Default group (all current and future inbounds)</label>
                        <div className="max-h-80 space-y-4 overflow-y-auto rounded-md border p-3">
                            {Object.entries(inbounds).map(([protocol, tags]) => <div key={protocol}><div className="mb-2 text-sm font-semibold capitalize">{protocol}</div><div className="space-y-2">{tags.map((tag) => <label key={`${protocol}-${tag}`} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={isDefault || (selected[protocol] || []).includes(tag)} disabled={isDefault || busy} onChange={() => toggle(protocol, tag)} /><span>{tag}</span></label>)}</div></div>)}
                            {!Object.keys(inbounds).length && <p className="text-sm text-muted-foreground">No inbounds loaded.</p>}
                        </div>
                        <div className="flex gap-2"><Button onClick={save} disabled={busy || !name.trim() || (!isDefault && !Object.values(selected).some((tags) => tags.length))}><Save className="mr-2 h-4 w-4" />{editing ? 'Save changes' : 'Create group'}</Button>{editing && <Button variant="outline" onClick={resetEditor}>Cancel</Button>}</div>
                    </CardContent></Card>

                    <Card><CardHeader><CardTitle>Groups for {panel || 'panel'}</CardTitle><CardDescription>Groups are only available on the panel where they were created.</CardDescription></CardHeader><CardContent className="space-y-3">{groups.map((group) => <div key={group.id} className="flex items-center justify-between gap-3 rounded-md border p-3"><div><div className="font-medium">{group.name} {group.is_default && <span className="text-xs text-primary">Default</span>}</div><div className="text-xs text-muted-foreground">{Object.values(group.inbounds).reduce((n, tags) => n + tags.length, 0)} inbounds</div></div><div className="flex gap-2"><Button variant="outline" size="sm" onClick={() => edit(group)}><Pencil className="h-4 w-4" /></Button><Button variant="destructive" size="sm" onClick={() => remove(group)}><Trash2 className="h-4 w-4" /></Button></div></div>)}{!groups.length && <p className="text-sm text-muted-foreground">No groups created for this panel.</p>}</CardContent></Card>
                </div>

                <Card><CardHeader><CardTitle>Assign groups to admins</CardTitle><CardDescription>Admins with no assigned groups keep the current inbound behavior. Choose one assigned group as the default for new users.</CardDescription></CardHeader><CardContent className="space-y-4">{admins.map((admin) => { const value = assignments[admin.id] || { ids: [], defaultId: null }; return <div key={admin.id} className="space-y-3 rounded-md border p-4"><div className="font-medium">{admin.username}</div><div className="flex flex-wrap gap-4">{groups.map((group) => <label key={group.id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={value.ids.includes(group.id)} onChange={() => toggleAdminGroup(admin.id, group.id)} />{group.name}</label>)}</div>{value.ids.length > 0 && <div className="max-w-sm space-y-2"><Label>Default for newly created users</Label><Select value={value.defaultId ? String(value.defaultId) : undefined} onValueChange={(v) => setAssignments((old) => ({ ...old, [admin.id]: { ...value, defaultId: Number(v) } }))}><SelectTrigger><SelectValue placeholder="Select default group" /></SelectTrigger><SelectContent>{groups.filter((g) => value.ids.includes(g.id)).map((group) => <SelectItem key={group.id} value={String(group.id)}>{group.name}</SelectItem>)}</SelectContent></Select></div>}<Button size="sm" onClick={() => saveAssignment(admin)}><Check className="mr-2 h-4 w-4" />Save assignment</Button></div>})}{!admins.length && <p className="text-sm text-muted-foreground">No reseller admins found for this panel.</p>}</CardContent></Card>
            </div>
        </PageLayout>
    )
}
