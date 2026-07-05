// Turn any API/axios error into a human-readable Persian "خطای <code> — <reason>"
// string, translating the server's message so the user sees the real cause.

const HTTP_REASONS: Record<number, string> = {
    400: 'درخواست نامعتبر',
    401: 'نشست منقضی شده؛ دوباره وارد شوید',
    403: 'دسترسی مجاز نیست (رد دسترسی یا رسیدن به سقف)',
    404: 'یافت نشد',
    405: 'متد مجاز نیست',
    408: 'زمان درخواست تمام شد',
    409: 'تداخل (از قبل وجود دارد)',
    413: 'حجم درخواست بیش از حد است',
    422: 'داده‌ی نامعتبر',
    429: 'درخواست بیش از حد',
    500: 'خطای سرور',
    501: 'پیاده‌سازی نشده',
    502: 'پاسخ نامعتبر از سرور مقصد (پنل در دسترس نیست)',
    503: 'سرویس در دسترس نیست (پنل مقصد خاموش است)',
    504: 'مهلت پاسخ سرور مقصد تمام شد',
}

// Exact English message -> Persian
const EXACT: Record<string, string> = {
    'Admin with this username already exists': 'ادمینی با این نام کاربری از قبل وجود دارد',
    'Admin not found': 'ادمین پیدا نشد',
    'Panel with this name already exists': 'پنلی با این نام از قبل وجود دارد',
    'Failed to connect to the panel with provided credentials': 'اتصال به پنل با اطلاعات واردشده ناموفق بود',
    'Panel not found': 'پنل پیدا نشد',
    'Only Marzban panels support inbound selection': 'فقط پنل‌های مرزبان از انتخاب inbound پشتیبانی می‌کنند',
    'Database file not found': 'فایل دیتابیس پیدا نشد',
    'Only .db files are allowed': 'فقط فایل‌های .db مجاز هستند',
    'News not found': 'خبر پیدا نشد',
    'Only image files are allowed': 'فقط فایل‌های تصویری مجاز هستند',
    'No logo set': 'لوگویی تنظیم نشده است',
    'Not authorized to access this resource.': 'اجازه‌ی دسترسی به این بخش را ندارید',
    'Could not validate credentials': 'اعتبارسنجی ناموفق بود؛ دوباره وارد شوید',
    'Access denied. Only superadmin can access this endpoint': 'دسترسی رد شد؛ فقط سوپرادمین به این بخش دسترسی دارد',
    'Incorrect username or password': 'نام کاربری یا رمز عبور اشتباه است',
    'No users found': 'کاربری یافت نشد',
    'Your admin account is inactive. Contact support.': 'حساب ادمین شما غیرفعال است. با پشتیبانی تماس بگیرید.',
    'This email is reserved by another admins': 'این ایمیل قبلاً توسط ادمین دیگری گرفته شده است',
    'This username already exists on the panel': 'این نام کاربری از قبل روی پنل وجود دارد',
    'Failed to create the user on the panel. Check the username and panel connection.':
        'ساخت کاربر روی پنل ناموفق بود. نام کاربری و اتصال پنل را بررسی کنید.',
    'User not found': 'کاربر پیدا نشد',
    'Failed to update user': 'به‌روزرسانی کاربر ناموفق بود',
    'Failed to reset user usage': 'ریست مصرف کاربر ناموفق بود',
    'Database restored successfully. Please restart the container to apply changes.':
        'دیتابیس با موفقیت بازیابی شد. برای اعمال تغییرات، کانتینر را ری‌استارت کنید.',
}

// Dynamic messages (regex). Use $1 for the captured part.
const PATTERNS: Array<[RegExp, string]> = [
    [/^Insufficient traffic to add this user, your limit: (.+)$/, 'حجم کافی برای ساخت این کاربر ندارید؛ سقف شما: $1'],
    [/^Insufficient traffic to update this user, your limit: (.+)$/, 'حجم کافی برای ویرایش این کاربر ندارید؛ سقف شما: $1'],
    [/^Insufficient traffic to reset usage for this user, your limit: (.+)$/, 'حجم کافی برای ریست این کاربر ندارید؛ سقف شما: $1'],
    [/^Failed to fetch inbounds: (.+)$/, 'دریافت inboundها ناموفق بود: $1'],
    [/^Failed to restore database: (.+)$/, 'بازیابی دیتابیس ناموفق بود: $1'],
    [/^Failed to retrieve logs: (.+)$/, 'دریافت لاگ‌ها ناموفق بود: $1'],
    [/^Failed to retrieve news: (.+)$/, 'دریافت اخبار ناموفق بود: $1'],
    [/^Failed to add news: (.+)$/, 'افزودن خبر ناموفق بود: $1'],
    [/^Failed to delete news: (.+)$/, 'حذف خبر ناموفق بود: $1'],
]

function translate(msg: string): string {
    if (!msg) return msg
    const trimmed = msg.trim()
    if (EXACT[trimmed]) return EXACT[trimmed]
    for (const [re, fa] of PATTERNS) {
        const m = trimmed.match(re)
        if (m) return fa.replace('$1', m[1] ?? '')
    }
    return msg
}

export function formatApiError(error: any): string {
    // No response at all (offline / DNS / CORS / timeout)
    if (error?.code === 'ERR_NETWORK' || (error?.request && !error?.response)) {
        return 'خطای شبکه — اتصال به سرور برقرار نشد'
    }

    const status: number | undefined = error?.response?.status
    const data = error?.response?.data

    let serverMsg = ''
    if (data && typeof data === 'object') {
        if (typeof data.message === 'string') {
            serverMsg = data.message
        } else if (typeof data.detail === 'string') {
            serverMsg = data.detail
        } else if (Array.isArray(data.detail)) {
            serverMsg = data.detail
                .map((d: any) => d?.msg || '')
                .filter(Boolean)
                .join('; ')
        }
    } else if (typeof data === 'string' && data) {
        serverMsg = data
    }

    const translated = translate(serverMsg)
    const reason = status ? HTTP_REASONS[status] || 'خطا' : ''

    if (status && translated) return `خطای ${status} — ${translated}`
    if (status) return `خطای ${status} — ${reason}`
    if (translated) return translated
    return error?.message || 'خطای ناشناخته'
}
