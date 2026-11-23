import type { ReactNode } from 'react'
import type {
    ProfitBlackFriday,
    ProfitMonth,
    ProfitReceivables,
    ProfitSelected,
    ProfitSettings,
} from '@/lib/api'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { fa, faPercent, versus, versusPoints } from './format'
import { Gb, Money, Num, Quiet, SectionCard, Stat } from './parts'
import { RankedBars, type RankedRow } from './RankedBars'
import { StackedBar } from './StackedBar'
import { TipRow, TipTitle } from './useChartTip'

/* ------------------------------------------------------------------ KPIs */

function Tile({
    label,
    value,
    unit,
    note,
    tone,
}: {
    label: string
    value: string
    unit?: string
    note: string
    tone?: 'accent' | 'negative'
}) {
    return (
        <Card className="min-w-0 p-4 sm:p-5">
            <p className="pf-caption text-muted-foreground">{label}</p>
            <p
                className={cn(
                    'mt-1 text-[1.375rem] font-black leading-snug',
                    tone === 'accent' && 'text-[color:var(--pf-positive)]',
                    tone === 'negative' && 'text-destructive'
                )}
            >
                <Num>{value}</Num>
                {unit && <span className="ms-1.5 text-[0.8125rem] font-normal text-muted-foreground">{unit}</span>}
            </p>
            <p className="pf-caption mt-1 text-muted-foreground">{note}</p>
        </Card>
    )
}

export function KpiTiles({ s }: { s: ProfitSelected }) {
    const p = s.previous
    return (
        <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3 xl:grid-cols-6">
            <Tile label="درآمد" value={fa(s.revenue)} unit="تومان" note={versus(s.revenue, p.revenue)} />
            <Tile label="سود ناخالص" value={fa(s.profit)} unit="تومان" note={versus(s.profit, p.profit)} />
            <Tile
                label="سود خالص"
                value={fa(s.net_profit)}
                unit="تومان"
                note={versus(s.net_profit, p.net_profit)}
                tone={s.net_profit < 0 ? 'negative' : 'accent'}
            />
            <Tile label="حاشیه سود" value={faPercent(s.margin, 1)} note={versusPoints(s.margin, p.margin)} />
            <Tile label="گیگ فروخته‌شده" value={fa(s.gb_sold)} unit="گیگ" note={versus(s.gb_sold, p.gb_sold)} />
            <Tile
                label="میانگین قیمت هر گیگ"
                value={s.avg_price_per_gb === null ? '—' : fa(s.avg_price_per_gb)}
                unit="تومان"
                note={s.avg_price_per_gb === null ? 'فروشی با گیگ ثبت‌شده نیست' : versus(s.avg_price_per_gb, p.avg_price_per_gb)}
            />
        </div>
    )
}

/* ---------------------------------------------------------------- target */

export function TargetCard({ s, settings }: { s: ProfitSelected; settings: ProfitSettings }) {
    const f = s.forecast
    const target = s.target
    const reached = target ? Math.min(1, target.progress) : 0
    return (
        <SectionCard
            title={s.is_current ? 'هدف و پیش‌بینی ماه جاری' : 'هدف فروش ماهانه'}
            subtitle={
                target ? (
                    <>
                        هدف: <Money value={target.amount} />
                    </>
                ) : (
                    'هدفی تعیین نشده است؛ از «تنظیمات محاسبه» می‌توانید آن را بگذارید.'
                )
            }
        >
            <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] lg:items-center lg:gap-10">
                <div>
                    {target ? (
                        <>
                            <div className="flex items-baseline justify-between gap-3">
                                <span className="pf-body text-muted-foreground">پیشرفت نسبت به هدف</span>
                                <span className="text-lg font-black">
                                    <Num>{faPercent(target.progress)}</Num>
                                </span>
                            </div>
                            <div
                                className="mt-2 h-2.5 w-full rounded-full"
                                style={{ background: 'var(--pf-o1)', opacity: 1 }}
                                role="progressbar"
                                aria-valuemin={0}
                                aria-valuemax={100}
                                aria-valuenow={Math.round(target.progress * 100)}
                            >
                                <div
                                    className="h-full rounded-full"
                                    style={{ width: `${reached * 100}%`, background: 'var(--pf-o5)' }}
                                />
                            </div>
                        </>
                    ) : (
                        <p className="pf-body text-muted-foreground">
                            با تعیین هدف، پیشرفت ماه در این‌جا نشان داده می‌شود.
                        </p>
                    )}
                </div>
                <dl className="grid grid-cols-2 gap-x-6 gap-y-3 md:grid-cols-4">
                    <Stat label={s.is_current ? 'درآمد تا امروز' : 'درآمد ماه'}>
                        <Money value={f ? f.month_to_date : s.revenue} unitClassName="pf-caption font-normal" />
                    </Stat>
                    {f && (
                        <>
                            <Stat label="پیش‌بینی درآمد پایان ماه">
                                <Money value={f.projected_revenue} unitClassName="pf-caption font-normal" />
                            </Stat>
                            <Stat label="پیش‌بینی سود خالص">
                                <Money
                                    value={f.projected_net_profit}
                                    className={cn(f.projected_net_profit < 0 && 'text-destructive')}
                                    unitClassName="pf-caption font-normal"
                                />
                            </Stat>
                            <Stat label="روزهای باقی‌مانده">
                                <Num>{fa(f.days_left)}</Num> <span className="pf-caption font-normal text-muted-foreground">روز</span>
                            </Stat>
                        </>
                    )}
                    {!f && settings.monthly_revenue_target > 0 && (
                        <Stat label="فاصله با هدف">
                            <Money
                                value={Math.max(0, settings.monthly_revenue_target - s.revenue)}
                                unitClassName="pf-caption font-normal"
                            />
                        </Stat>
                    )}
                </dl>
            </div>
            {f && (
                <p className="pf-caption mt-4 text-muted-foreground">
                    پیش‌بینی بر پایه‌ی میانگین {fa(f.days_elapsed)} روز گذشته از {fa(f.days_total)} روز این ماه است.
                </p>
            )}
        </SectionCard>
    )
}

/* -------------------------------------------------------------- payments */

export function MethodsCard({ s }: { s: ProfitSelected }) {
    const rows: RankedRow[] = (s.by_method ?? []).map((m) => ({
        key: m.key,
        label: m.label,
        value: Math.max(0, m.amount),
        display: (
            <>
                <Num>{faPercent(m.share)}</Num>
            </>
        ),
        tip: (
            <div>
                <TipTitle>{m.label}</TipTitle>
                <TipRow label="مبلغ" value={<Money value={m.amount} />} />
                <TipRow label="تعداد" value={fa(m.count)} />
                <TipRow label="سهم" value={faPercent(m.share, 1)} />
            </div>
        ),
        color: 'var(--pf-s1)',
    }))
    return (
        <SectionCard title="روش‌های پرداخت" subtitle="سهم هر روش از مبلغ دریافتی این ماه">
            {s.by_method === null ? (
                <Quiet />
            ) : rows.length === 0 ? (
                <Quiet>در این ماه دریافتی ثبت نشده است.</Quiet>
            ) : (
                <RankedBars rows={rows} ariaLabel="سهم روش‌های پرداخت" />
            )}
        </SectionCard>
    )
}

export function PriceBandsCard({ s }: { s: ProfitSelected }) {
    const bands = s.price_bands
    const totalGb = (bands ?? []).reduce((sum, b) => sum + b.gb, 0)
    const rows: RankedRow[] = (bands ?? []).map((b, i) => ({
        key: b.key,
        label: b.label,
        value: b.gb,
        display: <Gb value={b.gb} />,
        tip: (
            <div>
                <TipTitle>{b.label} تومان برای هر گیگ</TipTitle>
                <TipRow label="حجم" value={<Gb value={b.gb} />} />
                <TipRow label="درآمد" value={<Money value={b.revenue} />} />
                <TipRow label="تعداد فروش" value={fa(b.rows)} />
                {totalGb > 0 && <TipRow label="سهم از حجم" value={faPercent(b.gb / totalGb, 1)} />}
            </div>
        ),
        color: `var(--pf-o${i + 1})`,
    }))
    return (
        <SectionCard title="قیمت فروش هر گیگ" subtitle="حجم فروخته‌شده در هر بازه‌ی قیمتی (تومان)">
            {bands === null ? (
                <Quiet />
            ) : totalGb === 0 ? (
                <Quiet>در این ماه فروشی با حجم ثبت‌شده نیست.</Quiet>
            ) : (
                <RankedBars rows={rows} ariaLabel="حجم فروش در بازه‌های قیمتی" />
            )}
        </SectionCard>
    )
}

/* ------------------------------------------------------------- customers */

export function CustomersCard({ s }: { s: ProfitSelected }) {
    const c = s.concentration
    const parts =
        c && c.top1_share !== null && c.top5_share !== null
            ? [
                  { key: 'top1', label: 'بزرگ‌ترین پنل', share: c.top1_share, step: 5 as const },
                  { key: 'top5', label: 'چهار پنل بعدی', share: Math.max(0, c.top5_share - c.top1_share), step: 3 as const },
                  { key: 'rest', label: 'بقیه', share: Math.max(0, 1 - c.top5_share), step: 1 as const },
              ]
            : null
    return (
        <SectionCard title="مشتریان" subtitle="پنل‌هایی که در این ماه خرید کرده‌اند">
            <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
                <Stat label="خریداران فعال">
                    <Num>{fa(s.active_buyers)}</Num>
                </Stat>
                <Stat label="خریداران جدید">
                    <Num>{fa(s.new_buyers)}</Num>
                </Stat>
                <Stat label="خریداران ازدست‌رفته">
                    <Num>{fa(s.lost_buyers)}</Num>
                </Stat>
                <Stat label="درآمد هر پنل">
                    {s.arpu === null ? '—' : <Money value={s.arpu} unitClassName="pf-caption font-normal" />}
                </Stat>
            </dl>
            <div className="mt-6 border-t border-border pt-5">
                <h3 className="pf-body mb-3 font-bold tracking-normal">وابستگی به چند پنل بزرگ</h3>
                {parts ? (
                    <StackedBar
                        ariaLabel="سهم بزرگ‌ترین پنل‌ها از درآمد"
                        parts={parts.map((p) => ({
                            key: p.key,
                            label: p.label,
                            value: p.share,
                            step: p.step,
                            detail: <Num>{faPercent(p.share)}</Num>,
                        }))}
                    />
                ) : (
                    <Quiet>{c === null ? undefined : 'درآمدی برای محاسبه‌ی سهم نیست.'}</Quiet>
                )}
                {c?.top1_username && c.top1_share !== null && (
                    <p className="pf-caption mt-2 text-muted-foreground">
                        بزرگ‌ترین پنل: <span className="font-bold text-foreground">{c.top1_username}</span>
                    </p>
                )}
            </div>
        </SectionCard>
    )
}

/* ------------------------------------------------------------ receivables */

export function ReceivablesCard({ r }: { r: ProfitReceivables | null }) {
    const steps = [1, 2, 4, 5] as const
    return (
        <SectionCard title="مطالبات و بدهی‌ها" subtitle="وضعیت همین حالا، نه فقط این ماه">
            {r === null ? (
                <Quiet />
            ) : (
                <>
                    <dl className="grid grid-cols-2 gap-x-6 gap-y-4">
                        <Stat label="بدهی‌های باز (اعتباری)">
                            <Money value={r.debts_total} unitClassName="pf-caption font-normal" />
                            <span className="pf-caption block font-normal text-muted-foreground">
                                <Num>{fa(r.debts_count)}</Num> پنل
                            </span>
                        </Stat>
                        <Stat label="فاکتورهای پرداخت‌نشده">
                            <Money value={r.invoices_total} unitClassName="pf-caption font-normal" />
                            <span className="pf-caption block font-normal text-muted-foreground">
                                <Num>{fa(r.invoices_count)}</Num> فاکتور
                            </span>
                        </Stat>
                    </dl>
                    <div className="mt-6 border-t border-border pt-5">
                        <h3 className="pf-body mb-3 font-bold tracking-normal">عقب‌افتادگی پرداخت‌ها</h3>
                        <StackedBar
                            ariaLabel="مطالبات بر اساس مقدار تاخیر"
                            parts={r.aging.map((a, i) => ({
                                key: a.key,
                                label: a.label,
                                value: a.amount,
                                step: steps[i] ?? 5,
                                detail: (
                                    <>
                                        <Money value={a.amount} unitClassName="pf-caption font-normal" />
                                        <span className="ms-1 font-normal text-muted-foreground">
                                            · <Num>{fa(a.count)}</Num> مورد
                                        </span>
                                    </>
                                ),
                            }))}
                        />
                        {r.total === 0 && (
                            <p className="pf-caption mt-2 text-muted-foreground">هیچ مطالبه‌ی بازی وجود ندارد.</p>
                        )}
                    </div>
                    <div className="mt-6 border-t border-border pt-5">
                        <Stat label="موجودی کیف پول مشتریان">
                            <Money value={r.wallet_total} unitClassName="pf-caption font-normal" />
                        </Stat>
                        <p className="pf-caption mt-1 text-muted-foreground">
                            پولی که مشتریان نزد شما دارند و هنوز خرج نکرده‌اند ({fa(r.wallet_count)} کیف پول)؛ تعهد شماست، نه سود.
                        </p>
                    </div>
                </>
            )}
        </SectionCard>
    )
}

/* -------------------------------------------------------- unit economics */

export function UnitEconomicsCard({ s, settings }: { s: ProfitSelected; settings: ProfitSettings }) {
    const be = s.break_even_gb
    const progress = be && be > 0 ? Math.min(1, s.gb_sold / be) : be === 0 ? 1 : 0
    const consumption = s.consumption
    const usageRows: RankedRow[] = (consumption?.top_panels ?? []).map((p) => ({
        key: p.username,
        label: p.username,
        value: p.used_gb,
        display: <Gb value={p.used_gb} />,
        tip: (
            <div>
                <TipTitle>{p.username}</TipTitle>
                <TipRow label="مصرف" value={<Gb value={p.used_gb} />} />
                <TipRow label="سهم از کل مصرف" value={faPercent(p.share, 1)} />
            </div>
        ),
        color: 'var(--pf-s1)',
    }))
    return (
        <SectionCard title="بهره‌وری هر گیگ" subtitle="نقطه‌ی سر‌به‌سر و مصرف واقعی کاربران">
            <div>
                <h3 className="pf-body mb-2 font-bold tracking-normal">نقطه‌ی سر‌به‌سر</h3>
                {settings.fixed_monthly_cost <= 0 ? (
                    <p className="pf-body text-muted-foreground">
                        برای محاسبه‌ی نقطه‌ی سر‌به‌سر، هزینه‌های ثابت ماهانه را در «تنظیمات محاسبه» وارد کنید.
                    </p>
                ) : be === null ? (
                    <p className="pf-body text-muted-foreground">
                        قیمت فروش از هزینه‌ی هر گیگ بیشتر نیست؛ نقطه‌ی سر‌به‌سر قابل محاسبه نیست.
                    </p>
                ) : (
                    <>
                        <div className="flex items-baseline justify-between gap-3">
                            <span className="pf-body">
                                <Gb value={s.gb_sold} className="font-bold" />
                                <span className="text-muted-foreground"> از </span>
                                <Gb value={be} />
                            </span>
                            <span className="font-black">
                                <Num>{faPercent(be > 0 ? s.gb_sold / be : 1)}</Num>
                            </span>
                        </div>
                        <div className="mt-2 h-2.5 w-full rounded-full" style={{ background: 'var(--pf-o1)' }}>
                            <div className="h-full rounded-full" style={{ width: `${progress * 100}%`, background: 'var(--pf-o5)' }} />
                        </div>
                        <p className="pf-caption mt-1.5 text-muted-foreground">
                            {s.break_even_reached
                                ? 'فروش این ماه هزینه‌های ثابت را پوشش داده است.'
                                : 'هنوز به حجمی که هزینه‌های ثابت را پوشش دهد نرسیده‌اید.'}
                        </p>
                    </>
                )}
            </div>

            <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-4 border-t border-border pt-5">
                <Stat label="سود خالص هر گیگ">
                    {s.net_profit_per_gb === null ? (
                        '—'
                    ) : (
                        <Money
                            value={s.net_profit_per_gb}
                            className={cn(s.net_profit_per_gb < 0 && 'text-destructive')}
                            unitClassName="pf-caption font-normal"
                        />
                    )}
                </Stat>
                <Stat label="هزینه‌ی هر گیگ">
                    <Money value={settings.cost_per_gb} unitClassName="pf-caption font-normal" />
                </Stat>
            </dl>

            <div className="mt-5 border-t border-border pt-5">
                <h3 className="pf-body mb-3 font-bold tracking-normal">مصرف واقعی در برابر فروش</h3>
                {consumption ? (
                    <>
                        <dl className="mb-4 grid grid-cols-2 gap-x-6 gap-y-3">
                            <Stat label="مصرف کاربران">
                                <Gb value={consumption.used_gb} />
                            </Stat>
                            <Stat label="مصرف به فروش">
                                <Num>{faPercent(consumption.use_to_sold)}</Num>
                            </Stat>
                        </dl>
                        <p className="pf-caption mb-3 text-muted-foreground">پرمصرف‌ترین پنل‌ها</p>
                        <RankedBars rows={usageRows} ariaLabel="پرمصرف‌ترین پنل‌ها" />
                    </>
                ) : (
                    <p className="pf-body text-muted-foreground">داده‌ی مصرف برای این ماه موجود نیست.</p>
                )}
            </div>
        </SectionCard>
    )
}

/* ---------------------------------------------------------- black friday */

export function BlackFridayCard({ bf }: { bf: ProfitBlackFriday }) {
    const items: [string, ReactNode][] = [
        ['تعداد خرید', <Num key="a">{fa(bf.purchases)}</Num>],
        ['تعداد خریداران', <Num key="b">{fa(bf.buyers)}</Num>],
        ['گیگ پرداخت‌شده', <Gb key="c" value={bf.paid_gb} />],
        ['گیگ هدیه', <Gb key="d" value={bf.gift_gb} />],
        ['مبلغ دریافتی', <Money key="e" value={bf.card_amount + bf.wallet_amount} />],
        ['کارت به کارت', <Money key="f" value={bf.card_amount} />],
        ['کیف پول', <Money key="g" value={bf.wallet_amount} />],
        ['تخفیف داده‌شده', <Money key="h" value={bf.discount + bf.settlements_discount} />],
        ['تسویه‌های بدهی', <span key="i"><Num>{fa(bf.settlements)}</Num></span>],
        ['هزینه‌ی گیگ‌ها', <Money key="j" value={bf.cost} />],
    ]
    return (
        <SectionCard
            title={bf.active ? 'بلک‌فرایدی' : 'بلک‌فرایدی (پایان‌یافته)'}
            subtitle="نتیجه‌ی رویداد، جدا از بقیه‌ی فروش"
        >
            <dl className="grid grid-cols-2 gap-x-6 gap-y-4 md:grid-cols-3 xl:grid-cols-6">
                {items.map(([label, value]) => (
                    <Stat key={label} label={label}>
                        <span className="text-base font-bold">{value}</span>
                    </Stat>
                ))}
                <Stat label="سود رویداد">
                    <Money
                        value={bf.profit}
                        className={cn('font-black', bf.profit < 0 ? 'text-destructive' : 'text-[color:var(--pf-positive)]')}
                        unitClassName="pf-caption font-normal"
                    />
                </Stat>
            </dl>
        </SectionCard>
    )
}

/* -------------------------------------------------------------- misc */

export function UnknownGbNote({ s }: { s: ProfitMonth | ProfitSelected }) {
    if (s.unknown_gb_revenue <= 0) return null
    return (
        <p className="pf-caption text-muted-foreground">
            <Money value={s.unknown_gb_revenue} /> از درآمد این ماه، حجم (گیگ) ثبت‌شده ندارد؛ بنابراین هزینه‌ی آن در محاسبه‌ی سود
            نیامده است.
        </p>
    )
}
