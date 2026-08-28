import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { UserPlus, UserCog, UserMinus, HelpCircle } from 'lucide-react'

function FaqItem({ q, a }: { q: string; a: string }) {
    return (
        <div className="border-b border-border pb-3 last:border-0 last:pb-0">
            <p className="font-medium text-foreground mb-1">{q}</p>
            <p className="text-muted-foreground">{a}</p>
        </div>
    )
}

export function HelpPage() {
    return (
        <div dir="rtl" className="space-y-6 p-4 md:p-6 max-w-3xl">
            <div>
                <h1 className="text-2xl md:text-3xl font-bold tracking-tight">راهنما</h1>
                <p className="text-muted-foreground">آموزش کار با پنل و سوالات متداول</p>
            </div>

            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <UserPlus className="h-5 w-5 text-primary" /> ساخت کاربر
                    </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm leading-7 text-muted-foreground">
                    <p>۱. از داشبورد روی دکمه‌ی «Add User» بزنید.</p>
                    <p>۲. یک نام کاربری (Username) یکتا وارد کنید.</p>
                    <p>۳. حجم (Traffic) را به گیگابایت و انقضا (Expiry) را به روز بگذارید. برای بدون‌انقضا، فیلد انقضا را خالی بگذارید.</p>
                    <p>۴. روی «Create User» بزنید. اگر سهمیه‌ی حجم کافی نباشد یا نام تکراری باشد، علتش با پیام فارسی نمایش داده می‌شود.</p>
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <UserCog className="h-5 w-5 text-primary" /> ویرایش کاربر
                    </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm leading-7 text-muted-foreground">
                    <p>۱. در لیست کاربران، روی آیکون ویرایش (مداد) کنار کاربر بزنید.</p>
                    <p>۲. حجم یا تاریخ انقضا را تغییر دهید و ذخیره کنید.</p>
                    <p>۳. برای اضافه‌کردن حجم، مقدار Traffic را بیشتر کنید؛ فقط تفاوت از سهمیه‌ی شما کسر می‌شود.</p>
                    <p>نکته: اگر حجمِ کاربری که مصرف کرده را کم کنید، حجمِ مصرف‌شده به شما برنمی‌گردد؛ فقط بخش مصرف‌نشده.</p>
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <UserMinus className="h-5 w-5 text-primary" /> حذف کاربر
                    </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm leading-7 text-muted-foreground">
                    <p>۱. در لیست کاربران، روی آیکون حذف (سطل زباله) بزنید.</p>
                    <p>۲. تأیید کنید. در صورت فعال‌بودن «بازگشت حجم هنگام حذف»، حجمِ مصرف‌نشده‌ی کاربر به سهمیه‌ی شما برمی‌گردد.</p>
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <HelpCircle className="h-5 w-5 text-primary" /> سوالات متداول
                    </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4 text-sm leading-7">
                    <FaqItem
                        q="چرا نمی‌توانم کاربر بسازم؟"
                        a="یا سهمیه‌ی حجم کافی ندارید، یا نام کاربری تکراری است. متن خطای فارسی بالای فرم، علت دقیق را نشان می‌دهد."
                    />
                    <FaqItem
                        q="چرا با کم‌کردن حجمِ کاربرِ مصرف‌شده، چیزی به من برنمی‌گردد؟"
                        a="چون حجمی که کاربر مصرف کرده از بین رفته و قابل بازگشت نیست؛ فقط بخش مصرف‌نشده به سهمیه‌ی شما برمی‌گردد."
                    />
                    <FaqItem
                        q="«Online» و «Last online» یعنی چه؟"
                        a="Online یعنی کاربر همین الان به سرور متصل است. Last online زمان آخرین اتصال کاربر را نشان می‌دهد."
                    />
                    <FaqItem
                        q="چطور به یک کاربر حجم اضافه کنم؟"
                        a="کاربر را ویرایش کنید و مقدار Traffic را زیاد کنید؛ فقط تفاوت (مقدار اضافه‌شده) از سهمیه‌ی شما کسر می‌شود."
                    />
                    <FaqItem
                        q="کاربر ساختم ولی وصل نمی‌شود."
                        a="لینک اشتراک (Subscription) را درست به کاربر بدهید و مطمئن شوید اینباندِ انتخاب‌شده فعال است."
                    />
                    <FaqItem
                        q="سهمیه‌ی حجمِ باقی‌مانده‌ی من کجاست؟"
                        a="در داشبورد، کارت «Remaining Traffic» باقی‌مانده‌ی سهمیه‌ی شما را نشان می‌دهد."
                    />
                </CardContent>
            </Card>
        </div>
    )
}
