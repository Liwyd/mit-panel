import { useState } from 'react'
import { Plus, Trash2, Activity, Edit2, ShieldAlert } from 'lucide-react'
import { BotAPI, BotPanel } from '@/lib/bots-api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Empty, ErrorBox, Field, Loading, Notice, Spinner, Switch, selectClass, useAction, useLoad } from './common'

// mit-seller's IsMitType: new bots store "mit", rows written before the
// rebrand still say "nexra". Both mean this panel's own type, so the panel
// fields (URL, reseller credentials) are asked for either way.
const isMitPanelType = (type: string) => type === 'mit' || type === 'nexra'

const TYPES: Record<string, string> = {
    marzban: 'Marzban',
    mit: 'MIT Panel',
    nexra: 'Nexra Panel',
    marzneshin: 'Marzneshin',
    'x-ui_single': 'X-UI (سنایی)',
    alireza: 'X-UI علیرضا',
    s_ui: 'S-UI',
    wgdashboard: 'WGDashboard',
    mikrotik: 'MikroTik',
}

const TOGGLES: Array<[keyof BotPanel, string, string, string?]> = [
    ['status', 'activepanel', 'فعال (برای فروش نمایش داده شود)'],
    ['statusTest', 'ontestshowpanel', 'اکانت تست از این سرور'],
    ['sublink', 'onsublink', 'ارسال لینک اشتراک بعد از خرید'],
    ['configManual', 'onconfig', 'ارسال کانفیگ دستی بعد از خرید'],
    ['onholdstatus', 'ononhold', 'شروع زمان از اولین اتصال (on hold)'],
]

// What POST panels/{id}/test answers; a panel type without a test answers
// without `ok`, and an unreachable one carries the error text instead.
interface PanelTest {
    ok?: boolean | null
    version?: string
    remaining_gb?: number
    error?: string | object
}

// Superadmin only (the panel never shows this tab to admins, and both the
// panel and the bot refuse these calls with the admin's key).
export function PanelsTab({ api }: { api: BotAPI }) {
    const list = useLoad(() => api.get<BotPanel[]>('panels'), [api])
    const act = useAction()
    const [adding, setAdding] = useState(false)
    const [editing, setEditing] = useState<BotPanel | null>(null)
    const [tests, setTests] = useState<Record<string, PanelTest>>({})

    const update = async (p: BotPanel, body: Record<string, unknown>) => {
        const r = await act.run(() => api.put<BotPanel>(`panels/${p.id}`, body))
        if (r) list.reload()
        return r
    }

    if (list.loading && !list.data) return <Loading />

    return (
        <div className="space-y-4">
            <div className="flex items-start gap-2 rounded-lg border border-brand-gold/40 bg-brand-gold/10 p-3 text-sm">
                <ShieldAlert className="h-4 w-4 mt-0.5 shrink-0" />
                <span>این بخش فقط برای شماست. ادمین ربات فقط نام سرورها را می‌بیند و نمی‌تواند سرور اضافه، حذف یا ویرایش کند.</span>
            </div>
            <ErrorBox error={act.error || list.error} />
            <Notice text={act.notice} />
            <Card>
                <CardHeader className="flex flex-row items-center justify-between gap-3">
                    <div>
                        <CardTitle>سرورهای ربات</CardTitle>
                        <CardDescription>پنل‌هایی که ربات از آن‌ها سرویس می‌سازد.</CardDescription>
                    </div>
                    <Button size="sm" onClick={() => setAdding(true)}>
                        <Plus className="h-4 w-4 ml-1" /> افزودن سرور
                    </Button>
                </CardHeader>
                <CardContent className="space-y-3">
                    {!list.data?.length && <Empty text="سروری تعریف نشده" />}
                    {list.data?.map((p) => {
                        const test = tests[p.id]
                        return (
                            <div key={p.id} className="rounded-xl border border-border p-3 space-y-3">
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                    <div className="min-w-0">
                                        <div className="font-semibold flex items-center gap-2">
                                            {p.name_panel} <Badge variant="outline">{TYPES[p.type] || p.type}</Badge>
                                            {p.status !== 'activepanel' && <Badge variant="secondary">غیرفعال</Badge>}
                                        </div>
                                        <div className="text-xs text-muted-foreground truncate" dir="ltr">
                                            {p.url_panel}
                                        </div>
                                    </div>
                                    <div className="flex gap-1">
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            disabled={act.busy}
                                            onClick={async () => {
                                                const r = await act.run(() => api.post<PanelTest>(`panels/${p.id}/test`))
                                                if (r && r !== true) setTests((t) => ({ ...t, [p.id]: r }))
                                            }}
                                        >
                                            <Activity className="h-4 w-4 ml-1" /> تست
                                        </Button>
                                        <Button size="sm" variant="outline" onClick={() => setEditing(p)}>
                                            <Edit2 className="h-4 w-4" />
                                        </Button>
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            disabled={act.busy}
                                            onClick={async () => {
                                                if (!confirm(`سرور ${p.name_panel} از ربات حذف شود؟ سرویس‌های فروخته‌شده روی خود سرور می‌مانند.`)) return
                                                if (await act.run(() => api.del(`panels/${p.id}`))) list.reload()
                                            }}
                                        >
                                            <Trash2 className="h-4 w-4 text-destructive" />
                                        </Button>
                                    </div>
                                </div>
                                {test && (
                                    <div className={'rounded-lg p-2 text-xs ' + (test.ok ? 'bg-brand-green/10' : test.ok === false ? 'bg-destructive/10' : 'bg-muted/40')}>
                                        {test.ok ? 'اتصال برقرار است' : test.ok === false ? 'اتصال ناموفق' : 'برای این نوع تست اتصال نداریم'}
                                        {test.version && ` · نسخه ${test.version}`}
                                        {test.remaining_gb !== undefined && ` · حجم باقی‌مانده ${test.remaining_gb} گیگ`}
                                        {test.error != null && (
                                            <pre className="mt-1 whitespace-pre-wrap" dir="ltr">
                                                {typeof test.error === 'string' ? test.error : JSON.stringify(test.error)}
                                            </pre>
                                        )}
                                    </div>
                                )}
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                                    {TOGGLES.map(([k, on, label]) => (
                                        <Switch key={k} checked={p[k] === on} disabled={act.busy} onChange={(v) => update(p, { [k]: v })} label={label} />
                                    ))}
                                </div>
                            </div>
                        )
                    })}
                </CardContent>
            </Card>
            <AddPanelDialog
                open={adding}
                api={api}
                onClose={() => setAdding(false)}
                onSaved={() => {
                    setAdding(false)
                    list.reload()
                }}
            />
            <EditPanelDialog
                panel={editing}
                onClose={() => setEditing(null)}
                onSave={async (body) => {
                    if (editing && (await update(editing, body))) setEditing(null)
                }}
                busy={act.busy}
                error={act.error}
            />
        </div>
    )
}

function AddPanelDialog({ open, api, onClose, onSaved }: { open: boolean; api: BotAPI; onClose: () => void; onSaved: () => void }) {
    const empty = {
        name: '',
        type: 'marzban',
        url: '',
        username: '',
        password: '',
        inboundid: '',
        linksubx: '',
        marzban_url_direct: '',
        marzban_username_direct: '',
        marzban_password_direct: '',
    }
    const [f, setF] = useState(empty)
    const act = useAction()
    const set = (k: keyof typeof empty, v: string) => setF((x) => ({ ...x, [k]: v }))
    const noUser = f.type === 's_ui' || f.type === 'wgdashboard'
    const pwLabel = f.type === 's_ui' || f.type === 'wgdashboard' ? 'توکن / کلید API' : 'رمز عبور'

    return (
        <Dialog
            open={open}
            onOpenChange={(o) => {
                if (!o) {
                    setF(empty)
                    act.setError(null)
                    onClose()
                }
            }}
        >
            <DialogContent dir="rtl" className="max-w-lg max-h-[90vh] overflow-y-auto">
                <DialogHeader className="pr-8 text-right">
                    <DialogTitle>افزودن سرور</DialogTitle>
                </DialogHeader>
                <div className="space-y-3">
                    <Field label="نام (همین در ربات به مشتری نشان داده می‌شود)">
                        <Input value={f.name} onChange={(e) => set('name', e.target.value)} placeholder="🇩🇪 آلمان" />
                    </Field>
                    <Field label="نوع پنل">
                        <select className={selectClass} value={f.type} onChange={(e) => set('type', e.target.value)}>
                            {Object.entries(TYPES).map(([k, v]) => (
                                <option key={k} value={k}>
                                    {v}
                                </option>
                            ))}
                        </select>
                    </Field>
                    <Field label={isMitPanelType(f.type) ? 'آدرس MIT Panel' : 'آدرس پنل'} hint={isMitPanelType(f.type) ? 'مثل https://panel.example.com/dashboard' : undefined}>
                        <Input dir="ltr" value={f.url} onChange={(e) => set('url', e.target.value)} placeholder="https://panel.example.com:8000" />
                    </Field>
                    {!noUser && (
                        <Field label={isMitPanelType(f.type) ? 'نام کاربری ادمین (ریسلر) در MIT' : 'نام کاربری'}>
                            <Input dir="ltr" value={f.username} onChange={(e) => set('username', e.target.value)} />
                        </Field>
                    )}
                    <Field label={pwLabel}>
                        <Input dir="ltr" type="password" autoComplete="off" value={f.password} onChange={(e) => set('password', e.target.value)} />
                    </Field>
                    {['x-ui_single', 'alireza', 'wgdashboard', 'mikrotik'].includes(f.type) && (
                        <Field label={f.type === 'wgdashboard' ? 'نام کانفیگ وایرگارد' : 'شناسه اینباند'}>
                            <Input dir="ltr" value={f.inboundid} onChange={(e) => set('inboundid', e.target.value)} />
                        </Field>
                    )}
                    {['x-ui_single', 'alireza'].includes(f.type) && (
                        <Field label="آدرس لینک اشتراک" hint="برای این نوع پنل لازم است؛ بدون آن ربات از این سرور نمی‌فروشد.">
                            <Input dir="ltr" value={f.linksubx} onChange={(e) => set('linksubx', e.target.value)} />
                        </Field>
                    )}
                    {isMitPanelType(f.type) && (
                        <div className="rounded-lg border border-border p-3 space-y-3">
                            <p className="text-xs text-muted-foreground">
                                ربات کاربر را از طریق MIT می‌سازد (تا از حجم ریسلر کم شود) و لینک‌ها را مستقیم از مرزبانِ پشت آن می‌خواند.
                            </p>
                            <Field label="آدرس مرزبان">
                                <Input dir="ltr" value={f.marzban_url_direct} onChange={(e) => set('marzban_url_direct', e.target.value)} placeholder="https://marzban.example.com:8000" />
                            </Field>
                            <Field label="نام کاربری مرزبان" hint="خالی = همان نام کاربری MIT">
                                <Input dir="ltr" value={f.marzban_username_direct} onChange={(e) => set('marzban_username_direct', e.target.value)} />
                            </Field>
                            <Field label="رمز مرزبان" hint="خالی = همان رمز MIT">
                                <Input dir="ltr" type="password" autoComplete="off" value={f.marzban_password_direct} onChange={(e) => set('marzban_password_direct', e.target.value)} />
                            </Field>
                        </div>
                    )}
                    <ErrorBox error={act.error} />
                    <div className="flex justify-end gap-2">
                        <Button variant="outline" onClick={onClose}>
                            انصراف
                        </Button>
                        <Button
                            disabled={act.busy || !f.name || !f.url}
                            onClick={async () => {
                                if (await act.run(() => api.post('panels', f))) {
                                    setF(empty)
                                    onSaved()
                                }
                            }}
                        >
                            {act.busy && <Spinner className="ml-2" />} افزودن
                        </Button>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    )
}

function EditPanelDialog({
    panel,
    onClose,
    onSave,
    busy,
    error,
}: {
    panel: BotPanel | null
    onClose: () => void
    onSave: (body: Record<string, unknown>) => void
    busy: boolean
    error: string | null
}) {
    const [f, setF] = useState<Record<string, string>>({})
    const [key, setKey] = useState('')
    if ((panel?.id || '') !== key) {
        setKey(panel?.id || '')
        setF(
            panel
                ? {
                      name: panel.name_panel,
                      url_panel: panel.url_panel || '',
                      username_panel: panel.username_panel || '',
                      password_panel: '',
                      inboundid: panel.inboundid || '',
                      linksubx: panel.linksubx || '',
                      MethodUsername: panel.MethodUsername || '',
                      marzban_url_direct: panel.marzban_url_direct || '',
                      marzban_username_direct: panel.marzban_username_direct || '',
                      marzban_password_direct: '',
                  }
                : {}
        )
    }
    const set = (k: string, v: string) => setF((x) => ({ ...x, [k]: v }))
    const save = () => {
        if (!panel) return
        const body: Record<string, string> = {}
        const orig: Record<string, string> = {
            name: panel.name_panel,
            url_panel: panel.url_panel || '',
            username_panel: panel.username_panel || '',
            inboundid: panel.inboundid || '',
            linksubx: panel.linksubx || '',
            MethodUsername: panel.MethodUsername || '',
            marzban_url_direct: panel.marzban_url_direct || '',
            marzban_username_direct: panel.marzban_username_direct || '',
        }
        for (const [k, v] of Object.entries(f)) {
            if (k.endsWith('password_panel') || k === 'marzban_password_direct') {
                if (v) body[k] = v
            } else if (v !== orig[k]) {
                body[k] = v
            }
        }
        onSave(body)
    }

    return (
        <Dialog open={!!panel} onOpenChange={(o) => !o && onClose()}>
            <DialogContent dir="rtl" className="max-w-lg max-h-[90vh] overflow-y-auto">
                <DialogHeader className="pr-8 text-right">
                    <DialogTitle>ویرایش {panel?.name_panel}</DialogTitle>
                </DialogHeader>
                {panel && (
                    <div className="space-y-3">
                        <Field label="نام" hint="تغییر نام روی محصولات و سرویس‌های همین سرور هم اعمال می‌شود.">
                            <Input value={f.name || ''} onChange={(e) => set('name', e.target.value)} />
                        </Field>
                        <Field label="آدرس پنل">
                            <Input dir="ltr" value={f.url_panel || ''} onChange={(e) => set('url_panel', e.target.value)} />
                        </Field>
                        <Field label="نام کاربری">
                            <Input dir="ltr" value={f.username_panel || ''} onChange={(e) => set('username_panel', e.target.value)} />
                        </Field>
                        <Field label="رمز / توکن" hint={panel.password_set ? 'خالی بگذارید تا عوض نشود.' : undefined}>
                            <Input dir="ltr" type="password" autoComplete="off" value={f.password_panel || ''} onChange={(e) => set('password_panel', e.target.value)} />
                        </Field>
                        <Field label="شناسه اینباند / نام کانفیگ">
                            <Input dir="ltr" value={f.inboundid || ''} onChange={(e) => set('inboundid', e.target.value)} />
                        </Field>
                        <Field label="آدرس لینک اشتراک">
                            <Input dir="ltr" value={f.linksubx || ''} onChange={(e) => set('linksubx', e.target.value)} />
                        </Field>
                        <Field label="روش ساخت نام کاربری سرویس" hint="همان گزینه‌های منوی «روش ساخت نام کاربری» در ربات.">
                            <Input value={f.MethodUsername || ''} onChange={(e) => set('MethodUsername', e.target.value)} />
                        </Field>
                        {isMitPanelType(panel.type) && (
                            <>
                                <Field label="آدرس مرزبان">
                                    <Input dir="ltr" value={f.marzban_url_direct || ''} onChange={(e) => set('marzban_url_direct', e.target.value)} />
                                </Field>
                                <Field label="نام کاربری مرزبان">
                                    <Input dir="ltr" value={f.marzban_username_direct || ''} onChange={(e) => set('marzban_username_direct', e.target.value)} />
                                </Field>
                                <Field label="رمز مرزبان" hint="خالی بگذارید تا عوض نشود.">
                                    <Input dir="ltr" type="password" autoComplete="off" value={f.marzban_password_direct || ''} onChange={(e) => set('marzban_password_direct', e.target.value)} />
                                </Field>
                            </>
                        )}
                        <ErrorBox error={error} />
                        <div className="flex justify-end gap-2">
                            <Button variant="outline" onClick={onClose}>
                                انصراف
                            </Button>
                            <Button disabled={busy} onClick={save}>
                                {busy && <Spinner className="ml-2" />} ذخیره
                            </Button>
                        </div>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    )
}
