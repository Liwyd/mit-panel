import { useState } from 'react'
import { BotAPI } from '@/lib/bots-api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBox, Loading, Notice, useAction, useLoad } from '../bots/common'

type Item = { id: string; label: string }
type Menu = { layout: string[][]; labels: Record<string, string>; buttons: Record<string, { style?: string; icon_custom_emoji_id?: string }>; actions: Item[] }
type Config = Record<string, Menu>
const TITLES: Record<string, string> = { main: 'منوی کاربران متصل', unlinked: 'منوی کاربران بدون پنل', prospect: 'منوی کاربران جدید', superadmin: 'منوی اصلی سوپرادمین' }

export function TopupButtons({ api }: { api: BotAPI }) {
  const remote = useLoad(() => api.get<Config>('buttons'), [api])
  const [draft, setDraft] = useState<Config | null>(null)
  const act = useAction()
  if (remote.loading && !remote.data) return <Loading />
  if (!remote.data) return <ErrorBox error={remote.error} />
  const data = draft || remote.data
  const update = (menu: string, fn: (v: Menu) => Menu) => setDraft((d) => ({ ...(d || remote.data!), [menu]: fn((d || remote.data!)[menu]) }))
  const save = async () => {
    const payload = Object.fromEntries(Object.entries(data).map(([k, v]) => [k, { layout: v.layout, labels: v.labels, buttons: v.buttons }]))
    const result = await act.run(() => api.put<Config>('buttons', payload), 'ذخیره شد؛ از پیام بعدی اعمال می‌شود')
    if (result && result !== true) { remote.setData(result as Config); setDraft(null) }
  }
  return <div className="space-y-4">
    <Card><CardHeader><CardTitle>مدیریت دکمه‌های ربات</CardTitle><CardDescription>عنوان، ترتیب، رنگ و ایموجی دکمه‌های منوهای تلگرام را تنظیم کنید. شناسهٔ عمل هر دکمه ثابت می‌ماند.</CardDescription></CardHeader><CardContent className="space-y-5">
      {Object.entries(data).map(([menu, cfg]) => <section key={menu} className="space-y-3 rounded-xl border p-4"><h3 className="font-semibold">{TITLES[menu] || menu}</h3>{cfg.actions.map((action) => {
        const row = cfg.layout.findIndex((r) => r.includes(action.id)); const pos = cfg.layout[row]?.indexOf(action.id) ?? 0
        const move = (delta: number) => update(menu, (v) => { const flat = v.layout.flat(); const i = flat.indexOf(action.id); const j = Math.max(0, Math.min(flat.length - 1, i + delta)); [flat[i], flat[j]] = [flat[j], flat[i]]; const sizes = v.layout.map((r) => r.length); let n = 0; return { ...v, layout: sizes.map((size) => flat.slice(n, n += size)) } })
        return <div key={action.id} className="grid gap-2 md:grid-cols-[1fr_1.5fr_auto_auto_auto] items-center"><span className="text-xs text-muted-foreground">{action.label} · ردیف {row + 1} جایگاه {pos + 1}</span><Input maxLength={48} value={cfg.labels[action.id] || ''} placeholder={action.label} onChange={(e) => update(menu, (v) => ({ ...v, labels: { ...v.labels, [action.id]: e.target.value } }))} /><select className="rounded-md border bg-background p-2" value={cfg.buttons[action.id]?.style || ''} onChange={(e) => update(menu, (v) => ({ ...v, buttons: { ...v.buttons, [action.id]: { ...v.buttons[action.id], style: e.target.value } } }))}><option value="">خنثی</option><option value="primary">آبی</option><option value="success">سبز</option><option value="danger">قرمز</option></select><Input className="w-36" dir="ltr" placeholder="ID ایموجی اختیاری" value={cfg.buttons[action.id]?.icon_custom_emoji_id || ''} onChange={(e) => update(menu, (v) => ({ ...v, buttons: { ...v.buttons, [action.id]: { ...v.buttons[action.id], icon_custom_emoji_id: e.target.value } } }))} /><div className="flex gap-1"><Button variant="outline" size="sm" onClick={() => move(-1)}>↑</Button><Button variant="outline" size="sm" onClick={() => move(1)}>↓</Button></div></div>
      })}</section>)}
      <ErrorBox error={act.error} /><Notice text={act.notice} /><div className="flex gap-2"><Button disabled={act.busy || !draft} onClick={save}>ذخیره</Button><Button variant="outline" disabled={!draft} onClick={() => setDraft(null)}>لغو تغییرها</Button></div>
    </CardContent></Card>
  </div>
}
