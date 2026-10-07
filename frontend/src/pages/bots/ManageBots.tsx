import { useEffect, useState } from 'react'
import { Plus, Edit2, Trash2, RefreshCw, Link2 } from 'lucide-react'
import { botsAPI, TelegramBot, TelegramBotForm } from '@/lib/bots-api'
import { dashboardAPI } from '@/lib/api'
import { AdminOutput } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogHeader,
    AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { BotName, ErrorBox, Field, Notice, Spinner, Switch, selectClass, useAction } from './common'

const EMPTY: TelegramBotForm = { name: '', url: '', owner_key: '', manager_key: '', admin_id: null, is_active: true }

// Superadmin only: which bots the panel manages and which admin runs each.
export function ManageBots({ bots, onChange }: { bots: TelegramBot[]; onChange: () => void }) {
    const [admins, setAdmins] = useState<AdminOutput[]>([])
    const [editing, setEditing] = useState<TelegramBot | null>(null)
    const [open, setOpen] = useState(false)
    const [toDelete, setToDelete] = useState<TelegramBot | null>(null)
    const act = useAction()

    useEffect(() => {
        dashboardAPI.getAdmins().then(setAdmins).catch(() => setAdmins([]))
    }, [])

    return (
        <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-3">
                <div>
                    <CardTitle className="flex items-center gap-2">
                        <Link2 className="h-5 w-5 text-primary" /> اتصال ربات‌ها
                    </CardTitle>
                    <CardDescription>
                        فقط شما این بخش را می‌بینید. هر ربات را به یک ادمین بدهید تا از بخش «ربات» مدیریتش کند؛ ادمین به سرورها
                        (پنل‌ها) دسترسی ندارد.
                    </CardDescription>
                </div>
                <Button
                    size="sm"
                    onClick={() => {
                        setEditing(null)
                        setOpen(true)
                    }}
                >
                    <Plus className="h-4 w-4 ml-1" /> افزودن ربات
                </Button>
            </CardHeader>
            <CardContent className="space-y-3">
                <ErrorBox error={act.error} />
                <Notice text={act.notice} />
                {bots.length === 0 && (
                    <p className="text-sm text-muted-foreground">
                        هنوز رباتی وصل نشده. آدرس ربات و دو کلید API_OWNER_KEY و API_MANAGER_KEY را از فایل تنظیمات ربات
                        (/etc/nexrabot/botN.env) بردارید.
                    </p>
                )}
                {bots.map((b) => (
                    <div key={b.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border p-3">
                        <div className="min-w-0">
                            <div className="font-semibold flex items-center gap-2">
                                <BotName name={b.name} username={b.bot_username} usernameClass="text-xs text-muted-foreground" />
                                {!b.is_active && <Badge variant="secondary">غیرفعال</Badge>}
                            </div>
                            <div className="text-xs text-muted-foreground truncate" dir="ltr">
                                {b.url}
                            </div>
                            <div className="text-xs mt-1">
                                ادمین: {b.admin_username ? <b>{b.admin_username}</b> : <span className="text-muted-foreground">فقط خودتان</span>}
                            </div>
                        </div>
                        <div className="flex gap-1">
                            <Button
                                size="sm"
                                variant="outline"
                                disabled={act.busy}
                                onClick={() => act.run(() => botsAPI.check(b.id), `اتصال به ${b.name} برقرار است`)}
                            >
                                <RefreshCw className="h-4 w-4" />
                            </Button>
                            <Button
                                size="sm"
                                variant="outline"
                                onClick={() => {
                                    setEditing(b)
                                    setOpen(true)
                                }}
                            >
                                <Edit2 className="h-4 w-4" />
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => setToDelete(b)}>
                                <Trash2 className="h-4 w-4 text-destructive" />
                            </Button>
                        </div>
                    </div>
                ))}
            </CardContent>

            <BotDialog
                open={open}
                bot={editing}
                admins={admins}
                onClose={() => setOpen(false)}
                onSaved={() => {
                    setOpen(false)
                    onChange()
                }}
            />

            <AlertDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)}>
                <AlertDialogContent dir="rtl">
                    <AlertDialogHeader>
                        <AlertDialogTitle>قطع اتصال {toDelete?.name}</AlertDialogTitle>
                        <AlertDialogDescription>
                            ربات خاموش نمی‌شود و اطلاعاتش سر جایش می‌ماند؛ فقط از این پنل جدا می‌شود.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <div className="flex justify-end gap-3">
                        <AlertDialogCancel>انصراف</AlertDialogCancel>
                        <AlertDialogAction
                            className="bg-destructive"
                            onClick={async () => {
                                const b = toDelete
                                setToDelete(null)
                                if (b && (await act.run(() => botsAPI.remove(b.id)))) onChange()
                            }}
                        >
                            قطع اتصال
                        </AlertDialogAction>
                    </div>
                </AlertDialogContent>
            </AlertDialog>
        </Card>
    )
}

function BotDialog({
    open,
    bot,
    admins,
    onClose,
    onSaved,
}: {
    open: boolean
    bot: TelegramBot | null
    admins: AdminOutput[]
    onClose: () => void
    onSaved: () => void
}) {
    const [form, setForm] = useState<TelegramBotForm>(EMPTY)
    const act = useAction()

    useEffect(() => {
        if (!open) return
        act.setError(null)
        setForm(
            bot
                ? { name: bot.name, url: bot.url || '', owner_key: '', manager_key: '', admin_id: bot.admin_id, is_active: bot.is_active }
                : EMPTY
        )
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, bot])

    const set = <K extends keyof TelegramBotForm>(k: K, v: TelegramBotForm[K]) => setForm((f) => ({ ...f, [k]: v }))

    const save = async () => {
        const ok = await act.run(async () => {
            if (bot) {
                await botsAPI.update(bot.id, {
                    name: form.name,
                    url: form.url,
                    owner_key: form.owner_key || undefined,
                    manager_key: form.manager_key || undefined,
                    admin_id: form.admin_id ?? undefined,
                    unassign: form.admin_id === null,
                    is_active: form.is_active,
                })
            } else {
                await botsAPI.create(form)
            }
        })
        if (ok) onSaved()
    }

    return (
        <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
            <DialogContent dir="rtl" className="max-w-lg">
                <DialogHeader className="pr-8 text-right">
                    <DialogTitle>{bot ? `ویرایش ${bot.name}` : 'افزودن ربات'}</DialogTitle>
                    <DialogDescription>
                        پنل با هر دو کلید یک بار به ربات وصل می‌شود تا درستی‌شان را بسنجد. کلیدها به مرورگر ادمین‌ها نمی‌رسند.
                    </DialogDescription>
                </DialogHeader>
                <div className="space-y-3">
                    <Field label="نام">
                        <Input value={form.name} onChange={(e) => set('name', e.target.value)} placeholder="ربات ۷" />
                    </Field>
                    <Field label="آدرس ربات" hint="همان دامنه‌ای که وبهوک ربات روی آن است.">
                        <Input dir="ltr" value={form.url} onChange={(e) => set('url', e.target.value)} placeholder="https://bot7.example.com" />
                    </Field>
                    <Field label="کلید مالک (API_OWNER_KEY)" hint={bot ? 'خالی بگذارید تا عوض نشود.' : undefined}>
                        <Input dir="ltr" type="password" autoComplete="off" value={form.owner_key} onChange={(e) => set('owner_key', e.target.value)} />
                    </Field>
                    <Field label="کلید ادمین (API_MANAGER_KEY)" hint={bot ? 'خالی بگذارید تا عوض نشود.' : undefined}>
                        <Input dir="ltr" type="password" autoComplete="off" value={form.manager_key} onChange={(e) => set('manager_key', e.target.value)} />
                    </Field>
                    <Field label="ادمین این ربات">
                        <select
                            className={selectClass}
                            value={form.admin_id ?? ''}
                            onChange={(e) => set('admin_id', e.target.value === '' ? null : Number(e.target.value))}
                        >
                            <option value="">— هیچ‌کس (فقط خودم) —</option>
                            {admins.map((a) => (
                                <option key={a.id} value={a.id}>
                                    {a.username}
                                </option>
                            ))}
                        </select>
                    </Field>
                    <Switch checked={form.is_active} onChange={(v) => set('is_active', v)} label="فعال" hint="ربات غیرفعال برای ادمینش نمایش داده نمی‌شود." />
                    <ErrorBox error={act.error} />
                    <div className="flex justify-end gap-2 pt-2">
                        <Button variant="outline" onClick={onClose}>
                            انصراف
                        </Button>
                        <Button onClick={save} disabled={act.busy || !form.name || !form.url || (!bot && (!form.owner_key || !form.manager_key))}>
                            {act.busy && <Spinner className="ml-2" />} ذخیره
                        </Button>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    )
}
