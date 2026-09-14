"""User-facing strings (formal Persian)."""

START_LINKED = (
    "با سلام {name} عزیز 👋\n"
    "به ربات مدیریت پنل خوش آمدید.\n\n"
    "برای مشاهده‌ی پنل‌ها و موجودی هرکدام، «🗄 پنل‌های من» را انتخاب نمایید."
)
BALANCE_TEXT = "📊 موجودی حجم شما: {remaining_gb:.2f} / {initial_gb:.2f} گیگابایت (باقی‌مانده / کل اعتبار)"
START_UNLINKED = (
    "🛒 به فروشگاه MIT Panel خوش آمدید!\n\n"
    "برای خرید پنل VPN روی دکمه «درخواست پنل» کلیک کنید.\n"
    "برای مشاهده پنل‌های خود روی «پنل‌های من» کلیک کنید."
)
NOT_LINKED_RETRY = "⚠️ آیدی تلگرام شما هنوز در پنل ثبت نشده است. لطفاً همان پیام ابتدایی ربات را برای پشتیبانی فوروارد نمایید."
PANEL_UNREACHABLE = "⚠️ در حال حاضر ارتباط با پنل برقرار نشد. لطفاً چند دقیقه دیگر تلاش نمایید."

BTN_CANCEL = "❌ انصراف"
CANCELLED = "🚫 عملیات لغو شد."

BTN_TOPUP = "💳 شارژ حجم"
BTN_BALANCE = "📊 موجودی من"
BTN_CREATE_PANEL = "➕ ساخت پنل جدید"
CREATE_PANEL_SOON = "⏳ این امکان به‌زودی فعال خواهد شد."
BTN_CHANGE_PASSWORD = "🔑 تغییر رمز پنل"
ASK_CURRENT_PASSWORD = "🔒 برای تغییر رمز، ابتدا رمز عبور فعلی پنل خود را وارد نمایید:"
ASK_NEW_PASSWORD = "🔑 اکنون رمز عبور جدید را وارد نمایید:"
INVALID_PASSWORD = "⚠️ رمز عبور نمی‌تواند خالی باشد. لطفاً یک رمز عبور معتبر ارسال نمایید."
CURRENT_PASSWORD_WRONG = "🚫 رمز عبور فعلی نادرست است. عملیات لغو شد."
PASSWORD_CHANGE_FAILED = "⚠️ تغییر رمز ناموفق بود: {error}"
PASSWORD_APPLIED_ADMIN = "✅ رمز عبور پنل «{username}» با موفقیت تغییر کرد."
PASSWORD_CHANGE_NOTIFY_SUPERADMIN = (
    "🔑 ادمین «{username}» (آیدی عددی: {telegram_id}) رمز عبور پنل خود را تغییر داد.\n"
    "رمز جدید: <code>{new_password}</code>"
)

BTN_MESSAGE_USER = "✉️ پیام به کاربر"
ASK_MESSAGE_TEXT = "✉️ لطفاً متن پیامی که مایل به ارسال آن هستید را بنویسید:"
MESSAGE_SENT = "✅ پیام با موفقیت ارسال شد."
MESSAGE_FAILED = "⚠️ ارسال پیام ناموفق بود. احتمالاً کاربر ربات را مسدود کرده است."
INCOMING_MESSAGE_PREFIX = "📩 پیام از پشتیبانی:\n\n"

NEW_START_NOTIFICATION_LINKED = (
    "👤 کاربری ربات را استارت کرد\n"
    "نام: {full_name}\n"
    "یوزرنیم: {username}\n"
    "آیدی عددی: <code>{telegram_id}</code>\n"
    "وضعیت: متصل به ادمین «{admin_username}» ✅"
)
NEW_START_NOTIFICATION_UNLINKED = (
    "👤 کاربر جدیدی ربات را استارت کرد\n"
    "نام: {full_name}\n"
    "یوزرنیم: {username}\n"
    "آیدی عددی: <code>{telegram_id}</code>\n"
    "وضعیت: متصل نشده ⚠️"
)

SUPERADMIN_WELCOME = (
    "با سلام سوپرادمین محترم 👋\n"
    "با استارت هر کاربر جدید، یا ثبت درخواست شارژ/تغییر رمز، پیامی برای شما ارسال خواهد شد "
    "و می‌توانید مستقیماً از همان پیام نسبت به تأیید، رد یا ارسال پیام اقدام نمایید.\n\n"
    "درخواست‌های شارژ در انتظار بررسی و تنظیمات ربات نیز از دکمه‌های زیر در دسترس است."
)
BTN_PENDING_REQUESTS = "📋 درخواست‌های در انتظار"
NO_PENDING_REQUESTS = "ℹ️ در حال حاضر درخواست شارژ در انتظاری وجود ندارد."

FORCE_JOIN_TEXT = "📢 برای استفاده از ربات، ابتدا در کانال زیر عضو شوید و سپس «✅ عضو شدم» را بزنید."
FORCE_JOIN_CONFIRMED = "✅ عضویت شما تأیید شد. برای ادامه، دستور /start را ارسال نمایید."
BTN_TOGGLE_FORCE_JOIN = "🔀 روشن/خاموش‌کردن جوین اجباری"
BTN_SET_FORCE_JOIN_CHANNEL = "📢 تنظیم کانال جوین اجباری"
ASK_FORCE_JOIN_CHANNEL = "📢 لطفاً آیدی کانال را وارد نمایید (مثال: @channelusername):"
INVALID_CHANNEL = "⚠️ آیدی کانال معتبر نیست؛ باید با @ شروع شود."
FORCE_JOIN_CHANNEL_SET = "✅ کانال جوین اجباری با موفقیت روی {channel} تنظیم شد."
FORCE_JOIN_NO_CHANNEL_YET = "⚠️ ابتدا باید یک کانال برای جوین اجباری تنظیم نمایید."
FORCE_JOIN_BOT_NOT_ADMIN = (
    "⚠️ ربات در کانال {channel} دسترسی لازم را ندارد، بنابراین عضویت "
    "کاربران قابل بررسی نیست و همه بدون محدودیت وارد می‌شوند.\n\n"
    "لطفاً ربات را در آن کانال ادمین کنید و دوباره تلاش نمایید.\n"
    "علت: {error}"
)
FORCE_JOIN_CHECK_OK = "✅ دسترسی ربات به کانال {channel} بررسی و تأیید شد."
FORCE_JOIN_ENABLED_ON = "جوین اجباری فعال شد ✅"
FORCE_JOIN_ENABLED_OFF = "جوین اجباری غیرفعال شد 🚫"

BTN_SET_PRICE = "💰 تنظیم قیمت هر گیگابایت"
ASK_PRICE_PER_GB = "💰 لطفاً قیمت هر گیگابایت را به تومان وارد نمایید:"
INVALID_PRICE = "⚠️ عدد وارد شده معتبر نیست."
PRICE_SET_CONFIRM = "✅ قیمت هر گیگابایت با موفقیت روی {price:,} تومان تنظیم شد."

BTN_SET_CARD = "💳 تنظیم شماره کارت"
ASK_CARD_NUMBER = "💳 لطفاً شماره کارت جدید را وارد نمایید:"
INVALID_CARD_NUMBER = "⚠️ شماره کارت نمی‌تواند خالی باشد."
CARD_SET_CONFIRM = "✅ شماره کارت با موفقیت به‌روزرسانی شد."

BTN_SYNC_TELEGRAM_IDS = "🔄 همگام‌سازی آیدی از مرزبان"
SYNC_RUNNING = "⏳ در حال دریافت اطلاعات از مرزبان..."
SYNC_RESULT_NONE = "ℹ️ هیچ ادمین جدیدی برای همگام‌سازی پیدا نشد (یا آیدی‌ها از قبل ثبت شده، یا تو مرزبان هم خالی‌اند)."
SYNC_RESULT_HEADER = "✅ {count} ادمین به‌روزرسانی شد:\n\n"
SYNC_RESULT_LINE = "• {username} ← <code>{telegram_id}</code>\n"
SYNC_FAILED = "⚠️ همگام‌سازی با خطا مواجه شد: {error}"

ASK_AMOUNT_GB = "📊 لطفاً میزان حجم موردنیاز خود را به گیگابایت وارد نمایید:"
TOPUP_PRESETS = [500, 1000, 2000, 5000]
BTN_TOPUP_CUSTOM = "✏️ حجم دلخواه"
ASK_AMOUNT_GB_CHOICE = "📊 لطفاً میزان حجم موردنیاز خود را انتخاب نمایید:"
ASK_AMOUNT_GB_CUSTOM = "📊 حجم موردنظر را به گیگابایت وارد کنید:"
BELOW_MIN_GB = "⚠️ حداقل حجم قابل خرید {min_gb:g} گیگابایت است."
ABOVE_MAX_GB = "⚠️ حداکثر حجم قابل خرید {max_gb:g} گیگابایت است."
INVALID_AMOUNT_GB = "⚠️ عدد وارد شده معتبر نیست."
PRICE_NOT_SET = "⚠️ قیمت‌گذاری هنوز توسط پشتیبانی تنظیم نشده است. لطفاً بعداً تلاش نمایید یا با پشتیبانی تماس بگیرید."

INVOICE_TEXT = (
    "🧾 فاکتور شارژ حجم:\n\n"
    "مقدار: {gb:g} گیگابایت\n"
    "مبلغ قابل پرداخت: {price:,} تومان\n\n"
    "برای ادامه، پرداخت را انتخاب نمایید."
)
BTN_PAY = "💳 پرداخت"
PAYMENT_METHODS_TEXT = "💳 لطفاً روش پرداخت را انتخاب نمایید:"
BTN_PAY_CARD = "💳 کارت به کارت"
CARD_NOT_CONFIGURED = "⚠️ شماره کارت هنوز توسط پشتیبانی تنظیم نشده است. لطفاً با پشتیبانی تماس بگیرید."
CARD_PAYMENT_INSTRUCTIONS = (
    "💳 لطفاً مبلغ {price:,} تومان را به شماره کارت زیر واریز نمایید:\n\n"
    "<code>{card_number}</code>\n\n"
    "پس از واریز، تصویر رسید را ارسال نمایید."
)

BTN_PAY_WEEKLY = "🗓 پرداخت سر هفته"
WEEKLY_NOT_ENABLED = "🚫 این امکان برای شما فعال نیست!"
WEEKLY_TOPUP_SUCCESS = (
    "✅ {added_gb:g} گیگابایت به پنل «{username}» اضافه شد.\n"
    "📊 موجودی جدید: {new_gb:.2f} گیگابایت\n\n"
    "🗓 مبلغ {price:,} تومان به حساب این هفته‌ی شما اضافه شد.\n"
    "💳 بدهی فعلی: {debt:,} تومان"
)
WEEKLY_TOPUP_FAILED = "⚠️ ثبت شارژ ناموفق بود: {error}"
WEEKLY_REMINDER = (
    "🗓 یادآوری تسویه‌ی هفتگی\n\n"
    "▪️ پنل: {username}\n"
    "💰 مبلغ قابل پرداخت: {amount:,} تومان\n\n"
    "لطفاً تا پایان هفته نسبت به تسویه اقدام نمایید."
)
OVERDUE_REMINDER = (
    "⚠️ بدهی تسویه‌نشده\n\n"
    "▪️ پنل: {username}\n"
    "💰 مبلغ: {amount:,} تومان\n"
    "📅 {days} روز از موعد پرداخت گذشته است.\n\n"
    "لطفاً در اسرع وقت نسبت به تسویه اقدام نمایید."
)
BTN_PAY_DEBT = "💳 پرداخت"
DEBT_PAYMENT_INSTRUCTIONS = (
    "💳 لطفاً مبلغ {amount:,} تومان را به شماره کارت زیر واریز نمایید:\n\n"
    "<code>{card_number}</code>\n\n"
    "پس از واریز، تصویر رسید را ارسال نمایید."
)
NO_DEBT = "✅ در حال حاضر بدهی‌ای ثبت نشده است."
SETTLEMENT_SUBMITTED = "⏳ رسید تسویه ثبت شد. پس از بررسی، بدهی شما تسویه خواهد شد."
SETTLEMENT_APPROVED_ADMIN = "✅ تسویه‌ی شما تأیید شد. بدهی پنل «{username}» صفر شد."
SETTLEMENT_PARTIAL_ADMIN = (
    "✅ پرداخت {paid:,} تومان برای پنل «{username}» ثبت شد.\n"
    "💰 باقی‌مانده‌ی بدهی: {remaining:,} تومان"
)
SETTLEMENT_APPROVED_WITH_CREDIT = (
    "✅ تسویه‌ی شما تأیید شد. بدهی پنل «{username}» صفر شد.\n"
    "💼 مبلغ اضافه ({excess:,} تومان) به کیف پول شما افزوده شد. موجودی: {balance:,} تومان"
)

BTN_TOGGLE_WEEKLY = "🗓 فعال/غیرفعال‌کردن پرداخت هفتگی"
ASK_WEEKLY_USERNAME = "🗓 نام کاربری پنلی که می‌خواهید وضعیت پرداخت هفتگی‌اش تغییر کند را وارد نمایید:"
WEEKLY_ENABLED_ON = "✅ پرداخت هفتگی برای پنل «{username}» فعال شد."
WEEKLY_ENABLED_OFF = "🚫 پرداخت هفتگی برای پنل «{username}» غیرفعال شد."
WEEKLY_USED_NOTIFY_SUPERADMIN = (
    "🗓 خرید اعتباری (پرداخت سر هفته)\n\n"
    "▪️ پنل: {username}\n"
    "👤 آیدی عددی: {telegram_id}\n"
    "📊 حجم: {added_gb:g} گیگابایت\n"
    "💰 مبلغ: {price:,} تومان\n"
    "💳 مجموع بدهی: {debt:,} تومان"
)
WEEKLY_SETTLEMENT_LIST_HEADER = "🗓 تسویه‌ی هفتگی — وضعیت بدهی‌ها:\n\n"
WEEKLY_SETTLEMENT_LINE = "▫️ <b>{username}</b> — {amount:,} تومان{note}\n"
WEEKLY_SETTLEMENT_PAID_NOTE = " (از کیف پول تسویه شد ✅)"
WEEKLY_SETTLEMENT_NONE = "🗓 تسویه‌ی هفتگی: هیچ بدهی‌ای برای این هفته ثبت نشده است."
WEEKLY_WALLET_SETTLED = (
    "✅ بدهی هفتگی پنل «{username}» به مبلغ {paid:,} تومان از کیف پول شما تسویه شد.\n"
    "💼 موجودی کیف پول: {balance:,} تومان"
)
WEEKLY_WALLET_PARTIAL = (
    "🗓 زمان تسویه‌ی هفتگی رسید.\n\n"
    "▪️ پنل: {username}\n"
    "💼 از کیف پول کسر شد: {paid:,} تومان\n"
    "💰 باقی‌مانده جهت پرداخت: {remaining:,} تومان"
)

BTN_WALLET = "💼 کیف پول"
BTN_PAY_WALLET = "💼 پرداخت از کیف پول"
WALLET_BALANCE = "💼 موجودی کیف پول شما: {balance:,} تومان"
BTN_CHARGE_WALLET = "➕ شارژ کیف پول"
ASK_WALLET_AMOUNT = "➕ مبلغ موردنظر برای شارژ کیف پول را انتخاب نمایید:"
ASK_WALLET_CUSTOM_AMOUNT = "➕ مبلغ را به تومان وارد کنید:"
BTN_WALLET_CUSTOM = "✏️ مبلغ دلخواه"
WALLET_PRESETS = [1_000_000, 2_000_000, 5_000_000, 10_000_000]
INVALID_WALLET_AMOUNT = "⚠️ مبلغ وارد شده معتبر نیست."
WALLET_CHARGE_INSTRUCTIONS = (
    "💳 لطفاً مبلغ {amount:,} تومان را به شماره کارت زیر واریز نمایید:\n\n"
    "<code>{card_number}</code>\n\n"
    "پس از واریز، تصویر رسید را ارسال نمایید."
)
WALLET_CHARGE_SUBMITTED = "⏳ رسید شارژ کیف پول ثبت شد و پس از بررسی اعمال خواهد شد."
WALLET_CHARGED_ADMIN = (
    "✅ کیف پول شما {amount:,} تومان شارژ شد.\n💼 موجودی جدید: {balance:,} تومان"
)
WALLET_INSUFFICIENT = (
    "⚠️ موجودی کیف پول کافی نیست.\n"
    "💰 مبلغ فاکتور: {price:,} تومان\n"
    "💼 موجودی شما: {balance:,} تومان"
)
WALLET_PAID_SUCCESS = (
    "✅ {added_gb:g} گیگابایت به پنل «{username}» اضافه شد.\n"
    "📊 موجودی جدید پنل: {new_gb:.2f} گیگابایت\n"
    "💼 موجودی کیف پول: {balance:,} تومان"
)
BTN_GRANT_WALLET = "💼 شارژ کیف پول کاربر"
ASK_GRANT_WALLET_ID = "💼 آیدی عددی کاربری که می‌خواهید کیف پولش شارژ شود را وارد نمایید:"
ASK_GRANT_WALLET_AMOUNT = "💼 چه مبلغی (تومان) به کیف پول این کاربر اضافه شود؟"
GRANT_WALLET_SUCCESS = "✅ کیف پول کاربر {telegram_id} شارژ شد.\n💼 موجودی جدید: {balance:,} تومان"

BTN_DEBTS = "💰 بدهی‌ها"

ASK_RECEIPT = "🧾 لطفاً تصویر رسید واریز را ارسال نمایید."
NOT_A_PHOTO = "⚠️ فایل ارسالی تصویر نیست. لطفاً تصویر رسید را ارسال نمایید."

REQUEST_SUBMITTED = "⏳ درخواست شارژ شما ثبت شد. به‌زودی رسید شما بررسی خواهد شد."
REQUEST_APPROVED_ADMIN = (
    "✅ درخواست شارژ حجم شما تأیید شد.\n"
    "{added_gb:g} گیگابایت به حساب شما اضافه شد.\n"
    "موجودی جدید: {new_balance_gb:.2f} گیگابایت"
)
REQUEST_REJECTED_ADMIN = "❌ درخواست شارژ حجم شما رد شد."
REQUEST_REJECTED_ADMIN_WITH_REASON = "❌ درخواست شارژ حجم شما رد شد.\nعلت: {reason}"
ASK_REJECT_REASON = "📝 لطفاً علت رد درخواست را بنویسید (یا «-» در صورت عدم نیاز به توضیح):"

ALREADY_HANDLED = "ℹ️ این درخواست قبلاً بررسی شده است."
NOT_FOUND = "⚠️ درخواست یافت نشد."
APPROVED_TOAST = "تأیید شد ✅"
REJECTED_TOAST = "رد شد ❌"
PANEL_ERROR_TOAST = "⚠️ خطا در اتصال به پنل. درخواست به حالت در انتظار بازگشت."

BTN_MY_PANELS = "🗄 پنل‌های من"
NO_PANELS = "ℹ️ هیچ پنلی به حساب شما متصل نیست."
PANEL_ACTIVATION = (
    "🗄 هنوز پنلی به حساب شما متصل نیست.\n\n"
    "برای خرید پنل روی «درخواست پنل» کلیک کنید."
)
PANELS_LIST_HEADER = "▪️ پنل‌های شما:\n\n"
PANEL_LINE = (
    "▫️ <b>{username}</b>\n"
    "   📊 موجودی: {remaining_gb:.2f} / {initial_gb:.2f} گیگابایت\n"
    "   {expiry_line}\n"
)
PANEL_EXPIRY_LINE = "📅 انقضا: {expiry}"
PANEL_NO_EXPIRY = "📅 بدون تاریخ انقضا"
REFERRAL_PANELS_HEADER = "\n\n🎁 پنل‌های رفرال:\n\n"
REFERRAL_PANEL_LINE = (
    "▫️ <b>{username}</b> (🎁 رفرال)\n"
    "   📊 موجودی: {remaining_gb:.2f} / {initial_gb:.2f} گیگابایت\n"
    "   🔗 کد: {code}\n"
    "   👤 خریدار: {buyer_id}\n"
)
CHOOSE_PANEL = "▪️ لطفاً پنل موردنظر را انتخاب نمایید:"

WARN_100 = (
    "⚠️ حجم پنل «{username}» رو به اتمام است.\n"
    "📊 باقی‌مانده: {remaining_gb:.2f} گیگابایت\n\n"
    "برای جلوگیری از قطعی، پنل خود را شارژ نمایید."
)
WARN_50 = (
    "⚠️ حجم پنل «{username}» کمتر از ۵۰ گیگابایت است.\n"
    "📊 باقی‌مانده: {remaining_gb:.2f} گیگابایت\n\n"
    "لطفاً نسبت به شارژ پنل اقدام نمایید."
)
WARN_20 = (
    "⚠️ حجم پنل «{username}» کمتر از ۲۰ گیگابایت است!\n"
    "📊 باقی‌مانده: {remaining_gb:.2f} گیگابایت\n\n"
    "در صورت عدم شارژ، به‌زودی امکان ساخت کاربر جدید را نخواهید داشت."
)
WARN_EMPTY = (
    "🚫 حجم پنل «{username}» به پایان رسید.\n\n"
    "برای ادامه‌ی سرویس‌دهی، لطفاً پنل خود را شارژ نمایید."
)
BTN_TOPUP_THIS_PANEL = "💳 شارژ پنل"

BTN_FORECAST = "📈 پیش‌بینی مصرف"
FORECAST_TITLE = "📈 پیش بینی مصرف شما:\n\n"
FORECAST_BODY = (
    "▪️ پنل: <b>{username}</b>\n"
    "📊 مصرف {span_days} روز اخیر: {used_gb:.2f} گیگابایت\n"
    "📉 میانگین مصرف روزانه: {daily_gb:.2f} گیگابایت\n"
    "💾 موجودی فعلی: {remaining_gb:.2f} گیگابایت\n\n"
    "⏳ با این روند، حجم شما تا حدود <b>{days_left} روز</b> دیگر به پایان می‌رسد."
)
FORECAST_NO_DATA = (
    "▪️ پنل: <b>{username}</b>\n"
    "💾 موجودی فعلی: {remaining_gb:.2f} گیگابایت\n\n"
    "ℹ️ هنوز داده‌ی کافی برای پیش‌بینی جمع نشده است. از فردا در دسترس خواهد بود."
)
FORECAST_NO_USAGE = (
    "▪️ پنل: <b>{username}</b>\n"
    "💾 موجودی فعلی: {remaining_gb:.2f} گیگابایت\n\n"
    "✅ در روزهای اخیر مصرفی ثبت نشده است."
)
FORECAST_NO_PANELS = "ℹ️ پنلی برای پیش‌بینی مصرف یافت نشد."

BTN_ALL_PANELS = "🗄 همه پنل‌ها"
ALL_PANELS_HEADER = "📋 لیست کامل پنل‌ها ({count} مورد):\n\n"
ADMIN_PANEL_LINE = (
    "▫️ <b>{username}</b>{status}\n"
    "   📊 {remaining_gb:.2f} / {initial_gb:.2f} گیگابایت\n"
    "   👤 آیدی: {telegram_id}\n"
)
PANEL_INACTIVE_MARK = " (غیرفعال 🚫)"
BTN_GRANT_TRAFFIC = "➕ افزودن حجم"
ASK_GRANT_USERNAME = "➕ نام کاربری پنلی که می‌خواهید شارژ شود را وارد نمایید:"
ASK_GRANT_AMOUNT = "➕ چند گیگابایت به پنل «{username}» اضافه شود؟"
GRANT_SUCCESS = (
    "✅ {added_gb:g} گیگابایت به پنل «{username}» اضافه شد.\n"
    "📊 موجودی جدید: {new_gb:.2f} گیگابایت"
)
GRANT_FAILED = "⚠️ افزودن حجم ناموفق بود: {error}"
GRANT_NOTIFY_ADMIN = (
    "✨ حجم پنل «{username}» توسط پشتیبانی افزایش یافت.\n"
    "➕ {added_gb:g} گیگابایت اضافه شد.\n"
    "📊 موجودی جدید: {new_gb:.2f} گیگابایت"
)

BTN_PARTNERSHIP = "🤝 ثبت درخواست همکاری"
ASK_PARTNER_NAME = "🤝 لطفاً نام و نام خانوادگی خود را وارد نمایید:"
ASK_PARTNER_VOLUME = "📊 حجم فروش ماهانه‌ی شما چقدر است؟"
VOL_UNDER_1TB = "کمتر از ۱ ترابایت"
VOL_1TB = "۱ ترابایت"
VOL_2TB = "۲ ترابایت"
VOL_3TB = "۳ ترابایت"
VOL_OVER_3TB = "بالای ۳ ترابایت"
ASK_PARTNER_METHOD = "🛒 نحوه‌ی فروش خود را توضیح دهید (از چه طریقی مشتری جذب می‌کنید؟):"
PARTNER_SUBMITTED = (
    "✅ درخواست شما ارسال شد.\n\n"
    "به‌زودی پشتیبانی با شما ارتباط خواهد گرفت. سپاس از شکیبایی شما 🙏"
)
PARTNER_NOTIFY_SUPERADMIN = (
    "🤝 درخواست همکاری جدید\n\n"
    "👤 نام: {name}\n"
    "📎 یوزرنیم: {mention}\n"
    "🆔 آیدی عددی: <code>{telegram_id}</code>\n"
    "📊 حجم فروش ماهانه: {volume}\n"
    "🛒 نحوه‌ی فروش: {method}"
)

BTN_SEARCH_USER = "🔍 جستجوی کاربر"
ASK_SEARCH_QUERY = "🔍 آیدی عددی تلگرام، یوزرنیم تلگرام یا نام کاربری پنل را وارد نمایید:"
USER_NOT_FOUND = "⚠️ کاربری با این مشخصات یافت نشد."
USER_PROFILE = (
    "👤 <b>{name}</b>\n"
    "🆔 آیدی عددی: <code>{telegram_id}</code>\n"
    "📎 یوزرنیم: {mention}\n"
    "💼 موجودی کیف پول: {wallet:,} تومان\n"
    "💳 جمع بدهی: {debt:,} تومان\n"
)
USER_PROFILE_PANELS = "\n▪️ پنل‌ها:\n{panels}"
USER_PROFILE_PANEL_LINE = "   • <b>{username}</b> — {remaining_gb:.2f} / {initial_gb:.2f} گیگابایت\n"
USER_PROFILE_NO_PANELS = "\n▪️ پنلی متصل نیست.\n"
USER_PROFILE_DEBTS = "\n💰 بدهی‌ها:\n{debts}"
USER_PROFILE_DEBT_LINE = "   • {username}: {amount:,} تومان\n"
USER_PROFILE_NO_DEBTS = "\n✅ بدهی ندارد.\n"
USER_PROFILE_INVOICES = "\n🧾 فاکتورهای باز:\n{invoices}"
USER_PROFILE_INVOICE_LINE = "   • #{id} — {amount:,} تومان ({description})\n"
USER_PROFILE_NO_INVOICES = "\n✅ فاکتور بازی ندارد.\n"
USER_PROFILE_HISTORY = "\n📜 آخرین تراکنش‌ها:\n{history}"
USER_PROFILE_HISTORY_LINE = "   • {kind} — {amount:,} تومان — {status} ({date})\n"
USER_PROFILE_NO_HISTORY = "\n📜 تراکنشی ثبت نشده.\n"

BTN_DEDUCT_WALLET = "➖ کسر از کیف پول"
BTN_INVOICE_FOR_USER = "🧾 صدور فاکتور"
BTN_DELETE_INVOICE = "🗑 حذف فاکتور"
ASK_DEDUCT_AMOUNT = "➖ چه مبلغی (تومان) از کیف پول این کاربر کسر شود؟"
DEDUCT_SUCCESS = "✅ {amount:,} تومان کسر شد.\n💼 موجودی جدید: {balance:,} تومان"
CHOOSE_INVOICE_TO_DELETE = "🗑 کدام فاکتور حذف شود؟"
INVOICE_DELETED = "✅ فاکتور #{id} حذف شد."
INVOICE_DELETE_FAILED = "⚠️ حذف فاکتور ممکن نبود (شاید قبلاً تسویه شده)."

KIND_LABELS = {
    "topup": "شارژ حجم",
    "wallet": "شارژ کیف پول",
    "settlement": "تسویه هفتگی",
    "invoice": "پرداخت فاکتور",
}
STATUS_LABELS = {
    "pending": "در انتظار ⏳",
    "approved": "تأیید ✅",
    "rejected": "رد ❌",
}

BTN_NEW_INVOICE = "🧾 صدور فاکتور"
ASK_INVOICE_TARGET = "🧾 آیدی عددی تلگرام شخصی که فاکتور برایش صادر می‌شود را وارد نمایید:"
ASK_INVOICE_AMOUNT = "💰 مبلغ فاکتور را به تومان وارد نمایید:"
ASK_INVOICE_DESCRIPTION = "📝 توضیحات فاکتور را بنویسید (بابت چه خدماتی است؟):"
ASK_INVOICE_DUE = "⏳ مهلت پرداخت را انتخاب نمایید:"
DUE_IMMEDIATE = "⚡️ فوری"
DUE_TODAY = "🕐 تا پایان امروز"
DUE_3_DAYS = "📅 ۳ روز"
DUE_1_WEEK = "📅 یک هفته"
DUE_NONE = "♾ بدون مهلت"
INVOICE_CREATED = (
    "✅ فاکتور #{id} صادر شد.\n\n"
    "👤 آیدی عددی: {telegram_id}\n"
    "💰 مبلغ: {amount:,} تومان\n"
    "⏳ مهلت: {due}\n\n"
    "فاکتور برای ایشان ارسال شد."
)
INVOICE_CREATE_NOT_DELIVERED = "⚠️ فاکتور ثبت شد اما ارسال آن به کاربر ناموفق بود (احتمالاً ربات را استارت نکرده)."
INVOICE_FOR_CUSTOMER = (
    "🧾 فاکتور جدید #{id}\n\n"
    "💰 مبلغ قابل پرداخت: {amount:,} تومان\n"
    "📝 بابت: {description}\n"
    "⏳ مهلت پرداخت: {due}\n\n"
    "برای پرداخت، دکمه‌ی زیر را بزنید."
)
INVOICE_REMINDER = (
    "⚠️ یادآوری فاکتور پرداخت‌نشده #{id}\n\n"
    "💰 مبلغ: {amount:,} تومان\n"
    "📝 بابت: {description}\n"
    "⏳ مهلت: {due}\n\n"
    "لطفاً در اسرع وقت نسبت به پرداخت اقدام نمایید."
)
BTN_PAY_INVOICE = "💳 پرداخت فاکتور"
INVOICE_PAYMENT_INSTRUCTIONS = (
    "💳 لطفاً مبلغ {amount:,} تومان را به شماره کارت زیر واریز نمایید:\n\n"
    "<code>{card_number}</code>\n\n"
    "پس از واریز، تصویر رسید را ارسال نمایید."
)
INVOICE_RECEIPT_SUBMITTED = "⏳ رسید فاکتور ثبت شد. پس از بررسی، فاکتور تسویه خواهد شد."
INVOICE_PAID_CUSTOMER = "✅ فاکتور #{id} تسویه شد. سپاس از پرداخت شما."
INVOICE_ALREADY_PAID = "ℹ️ این فاکتور قبلاً تسویه شده است."
INVOICE_NOT_FOUND = "⚠️ فاکتور یافت نشد."

BTN_INVOICES = "🧾 فاکتورهای باز"
NO_INVOICES = "✅ هیچ فاکتور پرداخت‌نشده‌ای وجود ندارد."
BTN_MY_INVOICES = "🧾 فاکتورهای من"
NO_MY_INVOICES = "✅ فاکتور پرداخت‌نشده‌ای ندارید."

BTN_CREATE_ADMIN = "🆕 ساخت پنل جدید (ادمین)"
ASK_NEW_ADMIN_USERNAME = "🆕 نام کاربری پنل جدید را وارد نمایید:"
ASK_NEW_ADMIN_PASSWORD = "🔑 رمز عبور پنل جدید را وارد نمایید:\n(حداقل ۸ کاراکتر، ترکیب حروف و عدد)"
ASK_NEW_ADMIN_PANEL = "▪️ پنل مرزبان مقصد را انتخاب نمایید:"
ASK_NEW_ADMIN_TRAFFIC = "📊 حجم اولیه را به گیگابایت وارد نمایید (۰ برای بدون حجم):"
ASK_NEW_ADMIN_EXPIRY = "📅 مدت اعتبار را به روز وارد نمایید (یا «-» برای بدون انقضا):"
ASK_NEW_ADMIN_TELEGRAM = "👤 آیدی عددی تلگرام کاربر را وارد نمایید (یا «-» برای خالی):"
CREATING_ADMIN = "⏳ در حال ساخت پنل..."
NO_MARZBAN_PANELS = "⚠️ هیچ پنل مرزبانی در سیستم ثبت نشده است."
CREATE_ADMIN_SUCCESS = (
    "✅ پنل جدید با موفقیت ساخته شد.\n\n"
    "🔗 لینک پنل: {url}\n"
    "👤 نام کاربری: <code>{username}</code>\n"
    "🔑 رمز عبور: <code>{password}</code>\n"
    "📊 حجم اولیه: {traffic_gb:g} گیگابایت\n"
    "📅 انقضا: {expiry}"
)
PANEL_CHOICE_EXPIRED = "⚠️ این فهرست منقضی شده است؛ لطفاً مجدداً از ابتدا اقدام نمایید."
CREATE_ADMIN_FAILED = "⚠️ ساخت پنل ناموفق بود: {error}"

BTN_ADD_PANEL = "➕ افزودن پنل مرزبان"
ASK_PANEL_NAME = "📝 نام پنل را وارد نمایید:"
ASK_PANEL_URL = "🔗 آدرس پنل مرزبان را وارد نمایید (مثال: https://panel.example.com):"
ASK_PANEL_ADMIN_USER = "👤 نام کاربری ادمین sudo مرزبان را وارد نمایید:"
ASK_PANEL_ADMIN_PASS = "🔑 رمز عبور ادمین sudo مرزبان را وارد نمایید:"
CREATING_PANEL = "⏳ در حال اتصال به پنل..."
PANEL_CREATED_OK = "✅ پنل <b>{name}</b> با موفقیت ثبت شد."
PANEL_CREATED_FAIL = "⚠️ ثبت پنل ناموفق بود: {error}"

BTN_SET_ADMIN_PRICE = "💰 تنظیم قیمت ویژه ادمین"
ASK_ADMIN_FOR_PRICE = "💰 نام کاربری ادمین را وارد نمایید:"
ASK_ADMIN_PRICE_VALUE = "💰 قیمت هر گیگابایت برای {admin} (تومان):\n(برای حذف قیمت ویژه عدد 0 را وارد کنید)"
ADMIN_PRICE_SET = "✅ قیمت ویژه {admin} روی {price:,} تومان تنظیم شد."
ADMIN_PRICE_CLEARED = "✅ قیمت ویژه {admin} حذف شد (از قیمت گلوبال پیروی می‌کند)."
ADMIN_NOT_FOUND = "⚠️ ادمینی با نام <b>{admin}</b> یافت نشد."
ADMIN_PRICES_LIST = "💰 قیمت‌های ویژه ادمین‌ها:\n\n{lines}"
ADMIN_PRICES_NONE = "ℹ️ هیچ قیمت ویژه‌ای تعریف نشده است."
ADMIN_PRICE_LINE = "• {admin}: {price:,} تومان/گیگ"
BTN_LIST_ADMIN_PRICE = "📋 لیست قیمت‌های ویژه"
BTN_CLEAR_ADMIN_PRICE = "🗑 حذف قیمت ویژه"

BTN_BROADCAST = "📣 پیام همگانی"
ASK_BROADCAST_TEXT = "📣 متن پیامی که برای همه‌ی کاربران ارسال شود را بنویسید:"
BROADCAST_RESULT = "📣 پیام همگانی ارسال شد.\n✅ موفق: {sent}\n❌ ناموفق: {failed}"
BROADCAST_PREFIX = "📣 اطلاعیه:\n\n"

BTN_TUTORIALS = "📚 آموزش‌ها"
NO_TUTORIALS = "ℹ️ هنوز آموزشی ثبت نشده است."
TUTORIALS_LIST_TEXT = "📚 لطفاً آموزش موردنظر را انتخاب نمایید:"
BTN_ADD_TUTORIAL = "➕ افزودن آموزش"
BTN_DELETE_TUTORIAL = "🗑 حذف آموزش"
BTN_VIEW_TUTORIALS = "👁 مشاهده آموزش‌ها"

# --- superadmin sections ---
BTN_SEC_PANELS = "🗄 مدیریت پنل‌ها"
BTN_SEC_FINANCE = "💳 امور مالی"
BTN_SEC_USERS = "👥 کاربران"
BTN_SEC_SETTINGS = "⚙️ تنظیمات"
BTN_BACK = "🔙 بازگشت"
SECTION_PANELS = "🗄 مدیریت پنل‌ها — یک گزینه را انتخاب نمایید:"
SECTION_FINANCE = "💳 امور مالی — یک گزینه را انتخاب نمایید:"
SECTION_USERS = "👥 کاربران — یک گزینه را انتخاب نمایید:"
SECTION_SETTINGS = "⚙️ تنظیمات — یک گزینه را انتخاب نمایید:"
SECTION_TUTORIALS = "📚 آموزش‌ها — یک گزینه را انتخاب نمایید:"
BACK_TO_MENU = "🔙 منوی اصلی"
TUTORIALS_DELETE_TEXT = "🗑 کدام آموزش حذف شود؟"
CONFIRM_DELETE_TUTORIAL = (
    "🗑 حذف آموزش «{title}»\n\n"
    "این عمل قابل بازگشت نیست؛ آیا مطمئن هستید؟"
)
BTN_CONFIRM_DELETE = "🗑 بله، حذف شود"
BTN_KEEP = "↩️ انصراف"
TUTORIAL_DELETED = "✅ آموزش «{title}» حذف شد."
TUTORIAL_NOT_FOUND = "⚠️ این آموزش پیش‌تر حذف شده است."
DELETE_CANCELLED = "↩️ حذف لغو شد."
ASK_TUTORIAL_TITLE = "📚 لطفاً عنوان آموزش را وارد نمایید:"
ASK_TUTORIAL_CONTENT = (
    "📎 محتوای آموزش را ارسال نمایید.\n\n"
    "▫️ می‌توانید پست موردنظر را از کانال آموزش‌ها فوروارد کنید (پیشنهادی — "
    "با ویرایش پست در کانال، آموزش هم به‌روز می‌شود)\n"
    "▫️ یا مستقیماً متن، عکس، ویدیو یا فایل بفرستید"
)
INVALID_TUTORIAL_CONTENT = "⚠️ نوع محتوای ارسالی پشتیبانی نمی‌شود. لطفاً متن، عکس، ویدیو یا فایل ارسال نمایید."
TUTORIAL_ADDED_CONFIRM = "✅ آموزش «{title}» با موفقیت اضافه شد."
TUTORIAL_UNAVAILABLE = (
    "⚠️ در حال حاضر این آموزش در دسترس نیست. لطفاً به پشتیبانی اطلاع دهید."
)

# --- one list of bills: invoices and weekly credit are the same thing to a customer ---
TIMING_OPEN = "♾ بدون مهلت"
TIMING_DUE_IN = "⏳ {days} روز تا موعد"
TIMING_DUE_TODAY = "⏳ موعد: امروز"
TIMING_OVERDUE = "⏰ {days} روز از موعد گذشته"
TIMING_OVERDUE_TODAY = "⏰ موعد امروز گذشت"
WHEN_TODAY = "امروز"
WHEN_DAYS_AGO = "{days} روز پیش"

BILLS_SUMMARY = (
    "🧾 <b>فاکتورهای باز</b>\n"
    "━━━━━━━━━━━━━━━\n"
    "💰 جمع کل مطالبات: <b>{total:,}</b> تومان\n"
    "👥 {customers} مشتری · 🧾 {count} مورد\n"
    "⏰ سررسید گذشته: {overdue_count} مورد — {overdue_total:,} تومان"
)
BILLS_CUSTOMER_HEADER = (
    "👤 <b>{name}</b> · {mention} · <code>{telegram_id}</code>\n"
    "💰 جمع بدهی: <b>{total:,}</b> تومان\n"
)
BILL_INVOICE_ITEM = (
    "\n🧾 فاکتور #{id} — <b>{amount:,}</b> تومان\n"
    "      📝 {description}\n"
    "      {timing}\n"
)
BILL_WEEKLY_ITEM = (
    "\n🗓 پرداخت هفتگی · {username} — <b>{amount:,}</b> تومان\n"
    "      {timing}\n"
)
BILL_LAST_WARNED = "      🔔 آخرین هشدار: {when}\n"
BTN_WARN_INVOICE = "⚠️ هشدار عدم پرداخت · فاکتور #{id}"
BTN_WARN_WEEKLY = "⚠️ هشدار عدم پرداخت · {username}"

MY_BILLS_SUMMARY = (
    "🧾 <b>بدهی‌های پرداخت‌نشده‌ی شما</b>\n"
    "💰 جمع بدهی: <b>{total:,}</b> تومان · {count} مورد"
)
MY_BILL_INVOICE = (
    "🧾 فاکتور #{id}\n\n"
    "💰 مبلغ قابل پرداخت: {amount:,} تومان\n"
    "📝 بابت: {description}\n"
    "{timing}\n\n"
    "برای پرداخت، دکمه‌ی زیر را بزنید."
)
MY_BILL_WEEKLY = (
    "🗓 پرداخت هفتگی\n\n"
    "▪️ پنل: {username}\n"
    "💰 مبلغ قابل پرداخت: {amount:,} تومان\n"
    "{timing}\n\n"
    "برای پرداخت، دکمه‌ی زیر را بزنید."
)

# Sent when the superadmin presses a warning button, but worded as a notice from
# the billing system itself, the same voice as the automatic reminders.
NONPAYMENT_WARNING = (
    "🔔 <b>اطلاعیه‌ی سیستم — عدم پرداخت</b>\n"
    "━━━━━━━━━━━━━━━\n"
    "{subject}\n"
    "💰 مبلغ بدهی: <b>{amount:,}</b> تومان\n"
    "{days_line}\n\n"
    "⛔️ در صورت عدم پرداخت، {service} شما به‌صورت خودکار معلق خواهد شد.\n"
    "برای جلوگیری از تعلیق، از دکمه‌ی زیر اقدام به پرداخت نمایید."
)
WARN_SUBJECT_INVOICE = "🧾 فاکتور #{id} — {description}"
WARN_SUBJECT_WEEKLY = "🗓 پرداخت هفتگی پنل «{username}»"
WARN_DAYS_OVERDUE = "⏰ {days} روز از موعد پرداخت بدهی شما گذشته است."
WARN_DAYS_SINCE_ISSUED = "⏰ {days} روز از ثبت بدهی شما گذشته است."
WARN_UNPAID = "⏰ بدهی شما هنوز تسویه نشده است."
WARN_SERVICE_PANEL = "پنل"
WARN_SERVICE_GENERIC = "سرویس"
WARNING_SENT_TOAST = "⚠️ هشدار ارسال شد."
WARNING_NOT_DELIVERED = "⚠️ ارسال هشدار ناموفق بود (احتمالاً کاربر ربات را مسدود کرده است)."
WARNING_BILL_GONE = "ℹ️ این بدهی دیگر باز نیست (احتمالاً تسویه شده است)."

# --- who may see the wallet, and so the card number ---
WALLET_NOT_AVAILABLE = "ℹ️ کیف پول پس از فعال‌شدن حساب شما در دسترس خواهد بود."
ACCOUNT_ACTIVATED = "💼 کیف پول و بخش فاکتورها برای حساب شما فعال شد."

# --- automatic approval ---
BTN_TOGGLE_AUTO_APPROVE = "🤖 تأیید خودکار رسیدها"
AUTO_APPROVE_ON = (
    "🤖 تأیید خودکار روشن شد.\n\n"
    "از این لحظه هر رسیدی که برسد، یک دقیقه بعد بدون بررسی تأیید می‌شود. "
    "رسید همچنان برای شما ارسال می‌شود و اگر در همان یک دقیقه «رد» را بزنید، تأیید نمی‌شود.\n\n"
    "رسیدهایی که از قبل در انتظار بوده‌اند دست نمی‌خورند."
)
AUTO_APPROVE_OFF = "✋ تأیید خودکار خاموش شد. رسیدها دوباره منتظر بررسی شما می‌مانند."
AUTO_APPROVE_CAPTION_NOTE = "\n\n🤖 تأیید خودکار روشن است — این رسید یک دقیقه پس از دریافت تأیید می‌شود."
AUTO_APPROVED_NOTICE = (
    "🤖 تأیید خودکار\n\n"
    "🧾 رسید #{id} — {kind}\n"
    "👤 آیدی عددی: <code>{telegram_id}</code>\n"
    "💰 مبلغ: {amount:,} تومان"
)
AUTO_APPROVE_FAILED_NOTICE = (
    "⚠️ تأیید خودکار رسید #{id} انجام نشد و برای بررسی دستی باقی ماند.\n"
    "علت: {reason}"
)


# --- shop mode ---
SHOP_WELCOME = "🛒 فروشگاه MIT Panel\n\nیکی از پلن‌های زیر را انتخاب کنید:"
SHOP_ASK_TRAFFIC = "📦 چند گیگابایت ترافیک نیاز دارید؟"
SHOP_CUSTOM_AMOUNT = "💡 مقدار دلخواه را وارد کنید (GB):"
SHOP_ASK_PANEL = "🖥 پنل مورد نظر را انتخاب کنید:"
SHOP_ASK_USERNAME = "👤 نام کاربری دلخواه خود را وارد کنید:"
SHOP_ASK_PASSWORD = "🔑 رمز عبور دلخواه خود را وارد کنید:\n(حداقل ۸ کاراکتر، ترکیب حروف و عدد)"
SHOP_USERNAME_TAKEN = "⚠️ این نام کاربری قبلاً استفاده شده. نام دیگری وارد کنید."
SHOP_PASSWORD_WEAK = "⚠️ رمز عبور باید حداقل ۸ کاراکتر و شامل حروف و عدد باشد."
SHOP_PANEL_INFO = "🖥 پنل: {panel}\n📦 ترافیک: {gb} GB\n💰 قیمت: {price:,} تومان"
SHOP_CARD_INSTRUCTIONS = (
    "💳 کارت بانکی:\n<code>{card}</code>\n\n"
    "مبلغ {price:,} تومان را به این کارت واریز کنید\n"
    "و سپس رسید پرداخت را ارسال نمایید."
)
SHOP_RECEIPT_PROMPT = "🧾 رسید پرداخت را ارسال کنید:"
SHOP_REQUEST_SUBMITTED = "✅ درخواست شما ثبت شد و در انتظار بررسی مدیریت است."
SHOP_REQUEST_APPROVED = (
    "🎉 پنل شما آماده است!\n\n"
    "🔗 لینک پنل: {url}\n"
    "👤 نام کاربری: <code>{username}</code>\n"
    "🔑 رمز عبور: <code>{password}</code>\n\n"
    "برای مدیریت پنل خود از منوی زیر استفاده کنید."
)
SHOP_REQUEST_REJECTED = "❌ درخواست شما رد شد.\nعلت: {reason}"
SHOP_ALREADY_PENDING = "⚠️ شما یک درخواست در حال بررسی دارید. لطفاً منتظر بمانید."
SHOP_ALREADY_HAS_PANEL = "⚠️ شما از قبل یک پنل دارید. هر اکانت تلگرام فقط امکان داشتن یک پنل را دارد."
SHOP_PANELS_HEADER = "🖥 پنل‌های موجود:"

# --- referral ---
REFERRAL_ASK_CODE = "🔑 کد رفرال را وارد کنید (یا رد شید):"
REFERRAL_INVALID = "❌ کد رفرال نامعتبر یا غیرفعال است."
REFERRAL_APPLIED = "✅ کد رفرال اعمال شد! قیمت ویژه: {price:,} تومان/GB"
REFERRAL_BONUS_NOTIFY = "🎉 {gb} GB ترافیک رایگان از رفرال {user} به پنل شما اضافه شد!"
REFERRAL_CODE_SET = "✅ کد رفرال «{code}» برای شما ایجاد شد.\nاین کد را با کاربران خود به اشتراک بگذارید."
REFERRAL_CODE_EXISTS = "⚠️ شما از قبل کد رفرال دارید: {code}"
REFERRAL_NO_CODE = "ℹ️ شما هنوز کد رفرال ندارید."
REFERRAL_CODES_HEADER = "🔑 کدهای رفرال:\n\n"
REFERRAL_CODE_LINE = "• کد: {code} | مالک: {owner} | بونوس: {bonus}% | قیمت: {price:,} | وضعیت: {status}"
REFERRAL_CODES_NONE = "ℹ️ هیچ کد رفرالی ثبت نشده."
REFERRAL_ASK_OWNER = "👤 آیدی عددی مالک رفرال را وارد کنید:"
REFERRAL_ASK_CODE_STR = "🔑 کد رفرال را وارد کنید:"
REFERRAL_ASK_BONUS = "📊 درصد بونوس رفرال را وارد کنید (مثلاً 12):"
REFERRAL_ASK_PRICE = "💰 قیمت هر GB برای کاربران رفرالی را وارد کنید (تومان):"
REFERRAL_CREATED = "✅ کد رفرال ایجاد شد."

# --- panel link ---
PANEL_LINK_INFO = (
    "🔗 لینک پنل: {url}\n"
    "👤 نام کاربری: <code>{username}</code>\n"
    "🔑 رمز عبور: <code>{password}</code>"
)

# --- panel request approval (superadmin) ---
PANEL_REQUEST_HEADER = "🛒 درخواست پنل جدید از @{username} (ID: <code>{telegram_id}</code>)"
PANEL_REQUEST_INFO = "🖥 پنل: {panel}\n📦 ترافیک: {gb} GB\n💰 مبلغ: {price:,} تومان"
PANEL_REQUEST_APPROVED = "✅ درخواست پنل تأیید و ایجاد شد."
PANEL_REQUEST_REJECTED = "❌ درخواست پنل رد شد."

# --- button labels ---
BTN_SKIP = "⏭ رد شدن"
BTN_MY_REFERRAL = "🔑 کد رفرال من"
BTN_REQUEST_PANEL = "🛒 درخواست پنل"
BTN_MANAGE_REFERRALS = "🔑 مدیریت رفرال‌ها"
BTN_ADD_REFERRAL_CODE = "➕ افزودن کد رفرال"
BTN_LIST_REFERRAL_CODES = "📋 لیست کدهای رفرال"
BTN_DISABLE_REFERRAL = "🚫 غیرفعال کردن کد"
BTN_APPROVE_REQUEST = "✅ تأیید"
BTN_REJECT_REQUEST = "❌ رد"

# --- delete panel ---
BTN_DELETE_ADMIN = "🗑 حذف پنل"
DELETE_ADMIN_ASK = "👤 نام کاربری پنلی که می‌خواهید حذف کنید را وارد نمایید:"
DELETE_ADMIN_CONFIRM = "⚠️ آیا از حذف پنل «{username}» مطمئن هستید؟"
DELETE_ADMIN_YES = "✅ بله، حذف شود"
DELETE_ADMIN_NO = "❌ خیر، انصراف"
DELETE_ADMIN_SUCCESS_SUPERADMIN = (
    "✅ پنل «{username}» از MIT Panel حذف شد.\n\n"
    "⚠️ لطفاً پنل مربوطه را به صورت دستی از مرزبان نیز حذف نمایید."
)
DELETE_ADMIN_SUCCESS_OWNER = "⚠️ پنل شما با نام کاربری «{username}» حذف شد."
DELETE_ADMIN_FAILED = "⚠️ حذف پنل ناموفق بود: {error}"
