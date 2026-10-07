import { useMemo, useState } from 'react'
import { Plus, RefreshCw, Sparkles, Trash2 } from 'lucide-react'
import { botAPI, botsAPI, EmojiPack, PushResult, TelegramBot } from '@/lib/bots-api'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBox, Loading, Notice, Spinner, useAction, useLoad } from './common'
import { PremiumEmoji } from './emoji'
import { loadPacks } from './ButtonsTab'

// Superadmin only: the premium emoji packs every bot may use. The panel sends
// their emoji ids to each bot, which then refuses any other premium emoji.
export function EmojiPacksCard({ bots }: { bots: TelegramBot[] }) {
    const packs = useLoad(() => loadPacks(true), [])
    const act = useAction()
    const [link, setLink] = useState('')
    const [pushed, setPushed] = useState<PushResult[] | null>(null)
    const viaBot = bots.find((b) => b.is_active) || bots[0]
    const api = useMemo(() => (viaBot ? botAPI(viaBot.id) : null), [viaBot])

    const after = (r: { packs?: EmojiPack[]; pushed: PushResult[] } | true | null) => {
        if (r && r !== true) {
            setPushed(r.pushed)
            loadPacks(true).then((p) => packs.setData(p))
        }
    }

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <Sparkles className="h-5 w-5 text-amber-500" /> پک‌های ایموجی پریمیوم
                </CardTitle>
                <CardDescription className="leading-6">
                    فقط ایموجی‌های همین پک‌ها روی دکمه‌ها و در متن‌های ربات‌ها قابل استفاده‌اند (در پنل و در منوی خود ربات). هر کدام از این‌ها را بگذارید:
                    لینک پک (روی ایموجی در تلگرام بزنید ← نام پک ← اشتراک‌گذاری)، شناسه‌ی ایموجی‌ها، یا کل پیامی که دکمه‌ی «🆔 شناسه ایموجی پریمیوم» ربات
                    می‌دهد. پک هر ایموجی خودش پیدا و کامل اضافه می‌شود.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
                {!viaBot ? (
                    <p className="text-sm text-muted-foreground">اول یک ربات وصل کنید؛ پک‌ها از طریق ربات خوانده می‌شوند.</p>
                ) : (
                    <form
                        className="flex flex-col gap-2 sm:flex-row sm:items-start"
                        onSubmit={async (e) => {
                            e.preventDefault()
                            const r = await act.run(() => botsAPI.addPack(link.trim()))
                            if (r && r !== true) {
                                setLink('')
                                act.setNotice(
                                    `اضافه شد: ${r.added.join('، ')}` + (r.already.length ? ` — از قبل بود: ${r.already.join('، ')}` : '') + '. برای ربات‌ها هم فرستاده شد.'
                                )
                            }
                            after(r)
                        }}
                    >
                        <Textarea
                            dir="ltr"
                            rows={link.includes('\n') ? 5 : 2}
                            value={link}
                            onChange={(e) => setLink(e.target.value)}
                            placeholder={'https://t.me/addemoji/…\n5310241962127820707 5933948939530145209 …'}
                        />
                        <Button type="submit" disabled={!link.trim() || act.busy} className="shrink-0">
                            {act.busy ? <Spinner className="ml-1" /> : <Plus className="h-4 w-4 ml-1" />} افزودن
                        </Button>
                    </form>
                )}
                <ErrorBox error={act.error || packs.error} />
                <Notice text={act.notice} />
                {packs.loading && !packs.data ? (
                    <Loading />
                ) : !packs.data?.packs.length ? (
                    <p className="text-sm text-muted-foreground">
                        {packs.data?.configured
                            ? 'هیچ پکی مجاز نیست؛ ربات‌ها ایموجی پریمیوم استفاده نمی‌کنند.'
                            : 'هنوز پکی اضافه نشده. تا اولین پک را اضافه نکنید، ربات‌ها مثل قبل محدودیتی ندارند.'}
                    </p>
                ) : (
                    packs.data.packs.map((p) => (
                        <div key={p.name} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border p-3">
                            <div className="min-w-0 space-y-1">
                                <div className="flex items-center gap-2">
                                    <b>{p.title}</b>
                                    <Badge variant="outline">{p.emojis.length.toLocaleString('fa-IR')} ایموجی</Badge>
                                </div>
                                <a className="text-xs text-primary" dir="ltr" href={`https://t.me/addemoji/${p.name}`} target="_blank" rel="noopener noreferrer">
                                    t.me/addemoji/{p.name}
                                </a>
                                {api && viaBot && (
                                    <div className="flex flex-wrap gap-1 text-xl">
                                        {p.emojis.slice(0, 12).map((e) => (
                                            <PremiumEmoji key={e.id} api={api} botKey={String(viaBot.id)} id={e.id} fallback={e.emoji} className="h-6 w-6" />
                                        ))}
                                    </div>
                                )}
                            </div>
                            <Button
                                size="sm"
                                variant="outline"
                                disabled={act.busy}
                                onClick={async () => {
                                    if (!confirm(`پک «${p.title}» حذف شود؟ آیکون‌های این پک روی دکمه‌ها دیگر نمایش داده نمی‌شوند.`)) return
                                    after(await act.run(() => botsAPI.removePack(p.name), 'پک حذف شد'))
                                }}
                            >
                                <Trash2 className="h-4 w-4 text-destructive" />
                            </Button>
                        </div>
                    ))
                )}
                {!!bots.length && (
                    <div className="flex flex-wrap items-center gap-2">
                        <Button
                            size="sm"
                            variant="outline"
                            disabled={act.busy}
                            onClick={async () => {
                                const r = await act.run(() => botsAPI.syncPacks(), 'برای ربات‌ها فرستاده شد')
                                if (r && r !== true) setPushed(r.pushed)
                            }}
                        >
                            <RefreshCw className="h-4 w-4 ml-1" /> ارسال دوباره به همه‌ی ربات‌ها
                        </Button>
                        {pushed?.map((x) => (
                            <Badge key={x.bot} variant={x.ok ? 'success' : 'destructive'} title={x.error || ''}>
                                {x.bot}: {x.ok ? 'اعمال شد' : 'نرسید'}
                            </Badge>
                        ))}
                    </div>
                )}
            </CardContent>
        </Card>
    )
}
