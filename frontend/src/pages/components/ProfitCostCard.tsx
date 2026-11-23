import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Coins, Loader2, Save } from 'lucide-react'
import { settingsAPI, type PanelSettings } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

interface Props {
    settings: PanelSettings | null
    onSaved: (settings: PanelSettings) => void
}

export function ProfitCostCard({ settings, onSaved }: Props) {
    const [cost, setCost] = useState('')
    const [saving, setSaving] = useState(false)

    useEffect(() => {
        if (settings) setCost(String(settings.cost_per_gb ?? ''))
    }, [settings])

    const save = async () => {
        const value = Number(cost)
        if (cost.trim() === '' || !Number.isFinite(value) || value < 0) {
            toast.error('Cost per GB must be a number of 0 or more')
            return
        }
        try {
            setSaving(true)
            const data = await settingsAPI.updateSettings({ cost_per_gb: value })
            onSaved(data)
            toast.success('Cost per GB saved')
        } catch (err) {
            toast.error(err instanceof Error && err.message ? err.message : 'Failed to save cost per GB')
        } finally {
            setSaving(false)
        }
    }

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <Coins className="h-5 w-5 text-primary" />
                    Profit
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
                <p className="text-sm text-muted-foreground">
                    What one GB costs you. The dashboard profit report subtracts it from every GB sold or given away.
                </p>
                <div className="space-y-2">
                    <Label htmlFor="cost-per-gb">Cost per GB (toman)</Label>
                    <Input
                        id="cost-per-gb"
                        type="number"
                        inputMode="decimal"
                        min={0}
                        step="any"
                        value={cost}
                        onChange={(e) => setCost(e.target.value)}
                        disabled={!settings}
                    />
                </div>
                <Button onClick={save} disabled={saving || !settings} className="w-full sm:w-auto">
                    {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                    Save
                </Button>
            </CardContent>
        </Card>
    )
}
