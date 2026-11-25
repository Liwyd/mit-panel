import { useState } from 'react'
import { toast } from 'sonner'
import { Loader2 } from 'lucide-react'
import { settingsAPI, type ProfitSettings } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { fa, faFactor, parseNumber } from './format'

type EditableKey = 'cost_per_gb' | 'traffic_multiplier' | 'fixed_monthly_cost' | 'monthly_revenue_target'

const FIELDS: { key: EditableKey; label: string; hint: string; min: number; max: number; decimal?: boolean }[] = [
    { key: 'cost_per_gb', label: 'هزینه هر گیگ', hint: 'تومان؛ بهای تمام‌شده‌ی هر گیگ ترافیک واقعی', min: 0, max: 1_000_000 },
    {
        key: 'traffic_multiplier',
        label: 'ضریب ترافیک',
        hint: 'اگر با مصرف ۱ مگابایت، ۱٫۴ مگابایت از اعتبار کم می‌شود، ۱٫۴ وارد کنید؛ ۱ یعنی بدون ضریب',
        min: 0.1,
        max: 10,
        decimal: true,
    },
    { key: 'fixed_monthly_cost', label: 'هزینه‌های ثابت ماهانه', hint: 'تومان؛ سرور، زیرساخت و حقوق در هر ماه', min: 0, max: 1_000_000_000_000 },
    { key: 'monthly_revenue_target', label: 'هدف فروش ماهانه', hint: 'تومان؛ صفر یعنی بدون هدف', min: 0, max: 1_000_000_000_000 },
]

export function SettingsDialog({
    open,
    onOpenChange,
    settings,
    onSaved,
}: {
    open: boolean
    onOpenChange: (open: boolean) => void
    settings: ProfitSettings
    onSaved: () => void
}) {
    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent dir="rtl" lang="fa" className="profit-page max-w-md">
                {/* Remounted on every open so the fields always start from what is saved. */}
                {open && <Form settings={settings} onClose={() => onOpenChange(false)} onSaved={onSaved} />}
            </DialogContent>
        </Dialog>
    )
}

function Form({ settings, onClose, onSaved }: { settings: ProfitSettings; onClose: () => void; onSaved: () => void }) {
    const [values, setValues] = useState<Record<EditableKey, string>>({
        cost_per_gb: fa(settings.cost_per_gb).replace(/٬/g, ''),
        traffic_multiplier: faFactor(settings.traffic_multiplier || 1),
        fixed_monthly_cost: fa(settings.fixed_monthly_cost).replace(/٬/g, ''),
        monthly_revenue_target: fa(settings.monthly_revenue_target).replace(/٬/g, ''),
    })
    const [saving, setSaving] = useState(false)

    const save = async () => {
        const parsed = {} as Record<EditableKey, number>
        for (const field of FIELDS) {
            const value = parseNumber(values[field.key])
            if (!Number.isFinite(value) || value < field.min || value > field.max) {
                toast.error(
                    field.decimal
                        ? `«${field.label}» باید عددی بین ${faFactor(field.min)} و ${faFactor(field.max)} باشد`
                        : `«${field.label}» باید عددی صفر یا بزرگ‌تر باشد`,
                )
                return
            }
            parsed[field.key] = value
        }
        try {
            setSaving(true)
            await settingsAPI.updateSettings(parsed)
            toast.success('تنظیمات محاسبه ذخیره شد')
            onSaved()
            onClose()
        } catch (err) {
            toast.error(err instanceof Error && err.message ? err.message : 'ذخیره‌ی تنظیمات انجام نشد')
        } finally {
            setSaving(false)
        }
    }

    return (
        <>
            <DialogHeader className="mt-5 text-start">
                <DialogTitle className="tracking-normal">تنظیمات محاسبه</DialogTitle>
                <DialogDescription className="pf-body">
                    این اعداد در همه‌ی محاسبه‌های سود این صفحه به کار می‌روند.
                </DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
                {FIELDS.map((field) => (
                    <div key={field.key} className="space-y-1.5">
                        <Label htmlFor={`profit-${field.key}`} className="pf-body font-bold">
                            {field.label}
                        </Label>
                        <Input
                            id={`profit-${field.key}`}
                            inputMode={field.decimal ? 'decimal' : 'numeric'}
                            autoComplete="off"
                            value={values[field.key]}
                            onChange={(e) => setValues((v) => ({ ...v, [field.key]: e.target.value }))}
                        />
                        <p className="pf-caption text-muted-foreground">{field.hint}</p>
                    </div>
                ))}
            </div>
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-start">
                <Button onClick={save} disabled={saving}>
                    {saving && <Loader2 className="me-2 h-4 w-4 animate-spin" />}
                    ذخیره
                </Button>
                <Button variant="outline" onClick={onClose} disabled={saving}>
                    انصراف
                </Button>
            </div>
        </>
    )
}
