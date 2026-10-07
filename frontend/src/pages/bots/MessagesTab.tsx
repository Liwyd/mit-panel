import { useState } from 'react'
import { Megaphone, Trash2, UserPlus, BookOpen, Plus, Edit2 } from 'lucide-react'
import { BotAPI, BotHelp } from '@/lib/bots-api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Empty, ErrorBox, Field, Notice, Spinner, num, useAction, useLoad } from './common'

export function MessagesTab({ api }: { api: BotAPI }) {
    return (
        <div className="space-y-4">
            <BroadcastCard api={api} />
            <AdminsCard api={api} />
            <HelpCard api={api} />
            <CancelRequestsCard api={api} />
        </div>
    )
}

function BroadcastCard({ api }: { api: BotAPI }) {
    const status = useLoad(() => api.get<{ pending: number; running: boolean }>('broadcast'), [api])
    const act = useAction()
    const [text, setText] = useState('')
    const running = !!status.data?.running && (status.data?.pending || 0) > 0

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <Megaphone className="h-5 w-5 text-primary" /> پیام همگانی
                </CardTitle>
                <CardDescription>به همه‌ی کاربران فعال، دقیقه‌ای ۲۰ نفر (تا تلگرام ربات را محدود نکند).</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
                {running && (
                    <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-brand-gold/15 p-3 text-sm">
                        <span>در حال ارسال؛ {num(status.data?.pending)} نفر مانده (حدود {Math.ceil((status.data?.pending || 0) / 20)} دقیقه).</span>
                        <Button
                            size="sm"
                            variant="outline"
                            disabled={act.busy}
                            onClick={async () => {
                                if (await act.run(() => api.del('broadcast'), 'ارسال متوقف شد')) status.reload()
                            }}
                        >
                            توقف
                        </Button>
                    </div>
                )}
                <Textarea rows={5} value={text} onChange={(e) => setText(e.target.value)} placeholder="متن پیام (HTML تلگرام مجاز است)" />
                <ErrorBox error={act.error || status.error} />
                <Notice text={act.notice} />
                <Button
                    disabled={act.busy || !text.trim() || running}
                    onClick={async () => {
                        if (!confirm('پیام برای همه‌ی کاربران فرستاده شود؟')) return
                        const r = await act.run(() => api.post<{ recipients: number }>('broadcast', { text }))
                        if (r && r !== true) {
                            act.setNotice(`ارسال شروع شد برای ${num(r.recipients)} کاربر`)
                            setText('')
                            status.reload()
                        }
                    }}
                >
                    {act.busy && <Spinner className="ml-2" />} ارسال همگانی
                </Button>
            </CardContent>
        </Card>
    )
}

function AdminsCard({ api }: { api: BotAPI }) {
    const list = useLoad(() => api.get<{ admins: string[]; main: string }>('admins'), [api])
    const act = useAction()
    const [id, setId] = useState('')
    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <UserPlus className="h-5 w-5 text-primary" /> ادمین‌های داخل ربات
                </CardTitle>
                <CardDescription>آیدی عددی تلگرام کسانی که منوی مدیریت ربات را می‌بینند و رسیدها برایشان می‌آید.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
                <div className="flex gap-2">
                    <Input dir="ltr" inputMode="numeric" value={id} onChange={(e) => setId(e.target.value.replace(/[^\d]/g, ''))} placeholder="123456789" />
                    <Button
                        disabled={act.busy || !id}
                        onClick={async () => {
                            if (await act.run(() => api.post('admins', { id }))) {
                                setId('')
                                list.reload()
                            }
                        }}
                    >
                        افزودن
                    </Button>
                </div>
                <ErrorBox error={act.error || list.error} />
                <div className="flex flex-wrap gap-2">
                    {list.data?.admins.map((a) => (
                        <span key={a} className="inline-flex items-center gap-2 rounded-full border border-border px-3 py-1 text-sm" dir="ltr">
                            {a}
                            {a === list.data?.main ? (
                                <span className="text-xs text-muted-foreground">(اصلی)</span>
                            ) : (
                                <button
                                    aria-label="حذف"
                                    onClick={async () => {
                                        if (!confirm(`ادمین ${a} حذف شود؟`)) return
                                        if (await act.run(() => api.del(`admins/${a}`))) list.reload()
                                    }}
                                >
                                    <Trash2 className="h-3.5 w-3.5 text-destructive" />
                                </button>
                            )}
                        </span>
                    ))}
                </div>
            </CardContent>
        </Card>
    )
}

function HelpCard({ api }: { api: BotAPI }) {
    const list = useLoad(() => api.get<BotHelp[]>('help'), [api])
    const act = useAction()
    const [editing, setEditing] = useState<BotHelp | null>(null)
    const [name, setName] = useState('')
    const [desc, setDesc] = useState('')

    const startEdit = (h: BotHelp | null) => {
        setEditing(h)
        setName(h?.name_os || '')
        setDesc(h?.Description_os || '')
    }

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <BookOpen className="h-5 w-5 text-primary" /> آموزش‌ها
                </CardTitle>
                <CardDescription>بخش «📚 آموزش» ربات. عکس و ویدیوی آموزش را از خود ربات اضافه کنید؛ اینجا متن‌ها را مدیریت می‌کنید.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
                {!list.data?.length ? (
                    <Empty text="آموزشی نیست" />
                ) : (
                    <div className="divide-y divide-border rounded-lg border border-border">
                        {list.data.map((h) => (
                            <div key={h.id} className="flex items-center justify-between gap-2 p-3">
                                <span className="min-w-0">
                                    <span className="block font-medium">{h.name_os}</span>
                                    <span className="block truncate text-xs text-muted-foreground">{h.Description_os}</span>
                                </span>
                                <span className="flex shrink-0 gap-1">
                                    <Button size="xs" variant="ghost" onClick={() => startEdit(h)}>
                                        <Edit2 className="h-4 w-4" />
                                    </Button>
                                    <Button
                                        size="xs"
                                        variant="ghost"
                                        onClick={async () => {
                                            if (!confirm(`«${h.name_os}» حذف شود؟`)) return
                                            if (await act.run(() => api.del(`help/${h.id}`))) list.reload()
                                        }}
                                    >
                                        <Trash2 className="h-4 w-4 text-destructive" />
                                    </Button>
                                </span>
                            </div>
                        ))}
                    </div>
                )}
                <div className="rounded-lg border border-border p-3 space-y-2">
                    <b className="text-sm">{editing ? `ویرایش «${editing.name_os}»` : 'آموزش جدید'}</b>
                    <Field label="عنوان (متن دکمه)">
                        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="اندروید" />
                    </Field>
                    <Field label="متن">
                        <Textarea rows={4} value={desc} onChange={(e) => setDesc(e.target.value)} />
                    </Field>
                    <ErrorBox error={act.error || list.error} />
                    <div className="flex gap-2">
                        <Button
                            disabled={act.busy || !name.trim() || !desc.trim()}
                            onClick={async () => {
                                const body = { name: name.trim(), description: desc }
                                const r = await act.run(() => (editing ? api.put(`help/${editing.id}`, body) : api.post('help', body)))
                                if (r) {
                                    startEdit(null)
                                    list.reload()
                                }
                            }}
                        >
                            {editing ? 'ذخیره' : (
                                <>
                                    <Plus className="h-4 w-4 ml-1" /> افزودن
                                </>
                            )}
                        </Button>
                        {editing && (
                            <Button variant="outline" onClick={() => startEdit(null)}>
                                انصراف
                            </Button>
                        )}
                    </div>
                </div>
            </CardContent>
        </Card>
    )
}

interface CancelRequest {
    id: string
    username: string
    id_user: string
    description?: string | null
    status: string
}

function CancelRequestsCard({ api }: { api: BotAPI }) {
    const list = useLoad(() => api.get<CancelRequest[]>('cancel-requests'), [api])
    const waiting = (list.data || []).filter((r) => r.status === 'waiting')
    return (
        <Card>
            <CardHeader>
                <CardTitle>درخواست‌های بازگشت وجه</CardTitle>
                <CardDescription>تأیید یا رد این درخواست‌ها از داخل ربات (پیام درخواست برای ادمین‌ها) انجام می‌شود.</CardDescription>
            </CardHeader>
            <CardContent>
                <ErrorBox error={list.error} />
                {!waiting.length ? (
                    <Empty text="درخواست بازی نیست" />
                ) : (
                    <div className="divide-y divide-border rounded-lg border border-border text-sm">
                        {waiting.map((r) => (
                            <div key={r.id} className="flex flex-wrap justify-between gap-2 p-3">
                                <span className="font-mono" dir="ltr">
                                    {r.username}
                                </span>
                                <span className="text-muted-foreground">
                                    کاربر <span dir="ltr">{r.id_user}</span>
                                    {r.description && r.description !== '0' ? ` · ${r.description}` : ''}
                                </span>
                            </div>
                        ))}
                    </div>
                )}
            </CardContent>
        </Card>
    )
}
