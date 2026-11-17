import { useEffect, useState } from 'react'
import { Loader2, Save, Tags } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { settingsAPI } from '@/lib/api'
import { NodeNamesPanel } from '@/types'

/**
 * Names admins see for Marzban nodes on their Analytics page, instead of the
 * names given in Marzban. Blank keeps Marzban's name; nodes given the same
 * name are shown to admins as one.
 */
export function NodeNamesCard(): JSX.Element | null {
    const [panels, setPanels] = useState<NodeNamesPanel[] | null>(null)
    const [drafts, setDrafts] = useState<Record<number, Record<string, string>>>({})
    const [saving, setSaving] = useState<number | null>(null)
    const [message, setMessage] = useState<{ panelId: number; text: string; ok: boolean } | null>(null)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        settingsAPI
            .getNodeNames()
            .then((list) => {
                setPanels(list)
                setDrafts(
                    Object.fromEntries(
                        list.map((p) => [p.panel_id, Object.fromEntries(p.nodes.map((n) => [n.key, n.name]))])
                    )
                )
            })
            .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load nodes'))
    }, [])

    const save = async (panelId: number) => {
        setSaving(panelId)
        setMessage(null)
        try {
            await settingsAPI.saveNodeNames(panelId, drafts[panelId] || {})
            setMessage({ panelId, text: 'Saved', ok: true })
        } catch (e) {
            setMessage({ panelId, text: e instanceof Error ? e.message : 'Failed to save', ok: false })
        } finally {
            setSaving(null)
        }
    }

    // Nothing to name without a Marzban panel.
    if (panels && panels.length === 0) return null

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <Tags className="h-5 w-5 text-primary" />
                    Node names
                </CardTitle>
                <p className="text-sm text-muted-foreground">
                    What admins see for each node in their Analytics page. Leave a name blank to show the Marzban
                    name; nodes with the same name are shown as one.
                </p>
            </CardHeader>
            <CardContent className="space-y-6">
                {error && <p className="text-sm text-destructive">{error}</p>}
                {!panels && !error && <p className="text-sm text-muted-foreground">Loading...</p>}
                {panels?.map((panel) => (
                    <div key={panel.panel_id} className="space-y-3">
                        {panels.length > 1 && <h3 className="text-sm font-semibold">{panel.panel_name}</h3>}
                        {!panel.reachable && (
                            <p className="text-xs text-amber-500">
                                Couldn't read this panel's nodes from Marzban; only the main server and nodes already
                                named are listed.
                            </p>
                        )}
                        <div className="grid gap-3 sm:grid-cols-2">
                            {panel.nodes.map((node) => (
                                <label key={node.key} className="space-y-1">
                                    <span className="block text-xs text-muted-foreground">
                                        {node.marzban_name}
                                        {node.key !== 'master' && <span className="opacity-60"> · #{node.key}</span>}
                                    </span>
                                    <Input
                                        value={drafts[panel.panel_id]?.[node.key] ?? ''}
                                        placeholder={node.marzban_name}
                                        maxLength={64}
                                        onChange={(e) =>
                                            setDrafts((d) => ({
                                                ...d,
                                                [panel.panel_id]: { ...d[panel.panel_id], [node.key]: e.target.value },
                                            }))
                                        }
                                    />
                                </label>
                            ))}
                        </div>
                        <div className="flex items-center justify-end gap-3">
                            {message?.panelId === panel.panel_id && (
                                <span className={message.ok ? 'text-sm text-emerald-500' : 'text-sm text-destructive'}>
                                    {message.text}
                                </span>
                            )}
                            <Button
                                onClick={() => save(panel.panel_id)}
                                disabled={saving !== null}
                                className="bg-primary hover:bg-primary/90 text-primary-foreground"
                            >
                                {saving === panel.panel_id ? (
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                ) : (
                                    <Save className="mr-2 h-4 w-4" />
                                )}
                                Save node names
                            </Button>
                        </div>
                    </div>
                ))}
            </CardContent>
        </Card>
    )
}
