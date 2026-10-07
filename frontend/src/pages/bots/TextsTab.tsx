import { useState } from 'react'
import { BotAPI, BotText } from '@/lib/bots-api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBox, Field, Loading, Notice, Spinner, useAction, useLoad } from './common'

export function TextsTab({ api }: { api: BotAPI }) {
    const remote = useLoad(() => api.get<BotText[]>('texts'), [api])
    // only what the user changed; everything else shows the stored text
    const [edits, setEdits] = useState<Record<string, string>>({})
    const act = useAction()

    if (remote.loading && !remote.data) return <Loading />
    if (!remote.data) return <ErrorBox error={remote.error} />

    const value = (t: { id: string; text: string }) => edits[t.id] ?? t.text
    const setValue = (id: string, v: string) => setEdits((e) => ({ ...e, [id]: v }))
    const changed = remote.data.filter((t) => value(t) !== t.text)

    return (
        <Card>
            <CardHeader>
                <CardTitle>متن‌های ربات</CardTitle>
                <CardDescription className="leading-6">
                    متن پیام‌ها و برچسب دکمه‌ها. HTML تلگرام (مثل &lt;b&gt; و &lt;code&gt;) پشتیبانی می‌شود. ایموجی پریمیوم به شکل{' '}
                    <code dir="ltr">&lt;tg-emoji emoji-id="شناسه"&gt;😀&lt;/tg-emoji&gt;</code> نوشته می‌شود؛ اگر متن را در خود ربات با ایموجی پریمیوم
                    بفرستید، ربات همین را خودکار می‌سازد.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                {remote.data.map((t) => (
                    <Field key={t.id} label={t.label} hint={t.button ? 'برچسب دکمه — کاربران با /start بعدی دکمه‌ی جدید را می‌گیرند.' : undefined}>
                        {t.button ? (
                            <Input value={value(t)} onChange={(e) => setValue(t.id, e.target.value)} />
                        ) : (
                            <Textarea rows={4} value={value(t)} onChange={(e) => setValue(t.id, e.target.value)} />
                        )}
                    </Field>
                ))}
                <ErrorBox error={act.error} />
                <Notice text={act.notice} />
                <div className="sticky bottom-2 flex gap-2 rounded-xl bg-card/90 backdrop-blur p-2 border border-border">
                    <Button
                        disabled={act.busy || changed.length === 0}
                        onClick={async () => {
                            const body = Object.fromEntries(changed.map((t) => [t.id, value(t)]))
                            const r = await act.run(() => api.put<BotText[]>('texts', body), 'ذخیره شد')
                            if (r && r !== true) {
                                remote.setData(r)
                                setEdits({})
                            }
                        }}
                    >
                        {act.busy && <Spinner className="ml-2" />} ذخیره {changed.length ? `(${changed.length})` : ''}
                    </Button>
                    <Button variant="outline" disabled={!changed.length} onClick={() => setEdits({})}>
                        برگرداندن
                    </Button>
                </div>
            </CardContent>
        </Card>
    )
}
