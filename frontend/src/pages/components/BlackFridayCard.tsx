import { useEffect, useState } from 'react'
import { Loader2, Save, Tag } from 'lucide-react'
import { settingsAPI, type PanelSettings } from '@/lib/api'
import { refreshBlackFriday } from '@/lib/black-friday'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

// The end is entered and shown in Tehran time, whatever zone the browser is in.
const TEHRAN_OFFSET = '+03:30'

function toTehranInput(iso: string | undefined): string {
    if (!iso) return ''
    const date = new Date(iso)
    if (Number.isNaN(date.getTime())) return ''
    const parts = Object.fromEntries(
        new Intl.DateTimeFormat('en-CA', {
            timeZone: 'Asia/Tehran',
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            hourCycle: 'h23',
        })
            .formatToParts(date)
            .map((p) => [p.type, p.value])
    )
    return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`
}

interface Props {
    settings: PanelSettings | null
    onSaved: (settings: PanelSettings) => void
}

export function BlackFridayCard({ settings, onSaved }: Props) {
    const [enabled, setEnabled] = useState(false)
    const [endsAt, setEndsAt] = useState('')
    const [message, setMessage] = useState('')
    const [saving, setSaving] = useState(false)

    useEffect(() => {
        if (!settings) return
        setEnabled(!!settings.black_friday_enabled)
        setEndsAt(toTehranInput(settings.black_friday_ends_at))
        setMessage(settings.black_friday_message ?? '')
    }, [settings])

    const ended = !!endsAt && new Date(`${endsAt}:00${TEHRAN_OFFSET}`).getTime() <= Date.now()

    const save = async () => {
        if (!endsAt) {
            alert('Set an end date first')
            return
        }
        try {
            setSaving(true)
            const data = await settingsAPI.updateSettings({
                black_friday_enabled: enabled,
                black_friday_ends_at: `${endsAt}:59${TEHRAN_OFFSET}`,
                black_friday_message: message.trim(),
            })
            onSaved(data)
            await refreshBlackFriday()
        } catch (err) {
            alert(err instanceof Error ? err.message : 'Failed to save the Black Friday theme')
        } finally {
            setSaving(false)
        }
    }

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <Tag className="h-5 w-5 text-primary" />
                    Black Friday theme
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
                <p className="text-sm text-muted-foreground">
                    A dark theme for the login page and the whole panel, with a countdown on every
                    dashboard. It switches itself off at the end time.
                </p>
                <label className="flex items-center gap-2 text-sm font-medium">
                    <input
                        type="checkbox"
                        className="h-4 w-4"
                        checked={enabled}
                        onChange={(e) => setEnabled(e.target.checked)}
                        disabled={!settings}
                    />
                    Turn on the Black Friday theme
                </label>
                <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                        <label className="text-sm font-medium" htmlFor="bf-ends">Ends at (Tehran time)</label>
                        <Input
                            id="bf-ends"
                            type="datetime-local"
                            value={endsAt}
                            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setEndsAt(e.target.value)}
                            disabled={!settings}
                        />
                        {enabled && ended && (
                            <p className="text-xs text-destructive">This time has passed, so the theme stays off</p>
                        )}
                    </div>
                    <div className="space-y-2">
                        <label className="text-sm font-medium" htmlFor="bf-message">Countdown message</label>
                        <Input
                            id="bf-message"
                            dir="auto"
                            maxLength={200}
                            placeholder="Optional, e.g. the discount you are running"
                            value={message}
                            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setMessage(e.target.value)}
                            disabled={!settings}
                        />
                    </div>
                </div>
                <Button onClick={save} disabled={!settings || saving}>
                    {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                    Save theme
                </Button>
            </CardContent>
        </Card>
    )
}
