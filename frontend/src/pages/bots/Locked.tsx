import { Lock, LifeBuoy } from 'lucide-react'
import { buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'

const SUPPORT_URL = 'https://t.me/MITsupports'

// What an admin without a bot sees: the section, blurred, behind a notice.
export function LockedBots() {
    return (
        <div className="relative min-h-[560px] overflow-hidden rounded-2xl border border-border">
            {/* a blurred, inert picture of the section */}
            <div aria-hidden className="pointer-events-none select-none space-y-4 p-4 blur-[6px] opacity-60">
                <div className="flex gap-2">
                    {['خلاصه', 'محصولات', 'پرداخت‌ها', 'کاربران', 'سرویس‌ها', 'دکمه‌ها', 'تأیید خودکار'].map((t, i) => (
                        <span key={t} className={cn('rounded-lg px-3 py-2 text-sm', i === 0 ? 'bg-primary text-primary-foreground' : 'bg-muted')}>
                            {t}
                        </span>
                    ))}
                </div>
                <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                    {['کاربران', 'سرویس‌های فعال', 'فروش ۲۴ ساعت', 'پرداخت‌های در انتظار'].map((t, i) => (
                        <div key={t} className="rounded-xl border border-border bg-card p-4">
                            <div className="text-xs text-muted-foreground">{t}</div>
                            <div className="mt-1 text-xl font-bold">{['۱٬۲۴۸', '۳۱۲', '۲۷', '۴'][i]}</div>
                        </div>
                    ))}
                </div>
                <div className="space-y-2 rounded-xl border border-border bg-card p-4">
                    {['۳۰ گیگ یک ماهه', '۶۰ گیگ سه ماهه', '۱۰۰ گیگ سه ماهه', 'نامحدود یک ماهه'].map((t) => (
                        <div key={t} className="flex justify-between rounded-lg bg-muted/40 p-3 text-sm">
                            <span>{t}</span>
                            <span>۱۲۰٬۰۰۰ تومان</span>
                        </div>
                    ))}
                </div>
                <div className="mx-auto h-64 max-w-sm rounded-3xl bg-gradient-to-b from-[#d6e4ec] to-[#c9dbe5]" />
            </div>

            <div className="absolute inset-0 flex items-center justify-center bg-background/30 p-4">
                <div className="w-full max-w-sm space-y-4 rounded-2xl border border-border bg-card/95 p-6 text-center shadow-2xl backdrop-blur">
                    <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-muted">
                        <Lock className="h-7 w-7 text-muted-foreground" />
                    </span>
                    <div className="space-y-1">
                        <b className="block text-lg">دسترسی به این بخش برای حساب شما فعال نشده است</b>
                        <p className="text-sm text-muted-foreground leading-6">جهت فعال‌سازی، لطفاً با پشتیبانی تماس بگیرید.</p>
                    </div>
                    <a
                        href={SUPPORT_URL}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={cn(buttonVariants({ variant: 'default' }), 'w-full gap-2')}
                    >
                        <LifeBuoy className="h-4 w-4" /> تماس با پشتیبانی
                    </a>
                </div>
            </div>
        </div>
    )
}
