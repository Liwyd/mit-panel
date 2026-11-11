import { getApiClient } from './api-client'
import { ResponseModel } from '@/types'

// The "Bot" section talks to the panel, which forwards to the bot's own
// management API with the right key (owner for the superadmin, manager for
// the assigned admin). See backend/api/bots/routers.py.

const api = getApiClient()

export interface TelegramBot {
    id: number
    name: string
    url: string | null
    admin_id: number | null
    admin_username: string | null
    bot_username: string | null
    is_active: boolean
    created_at: string | null
}

export interface TelegramBotForm {
    name: string
    url: string
    owner_key: string
    manager_key: string
    admin_id: number | null
    is_active: boolean
}

export interface ApkInfo {
    available: boolean
    size?: number
    updated_at?: string
    version?: string | null
    source?: string
    file?: string
}

function unwrap<T>(res: { data: ResponseModel<T> }): T {
    if (!res.data.success) {
        throw new Error(res.data.message || 'Request failed')
    }
    return res.data.data as T
}

export const botsAPI = {
    list: async (): Promise<TelegramBot[]> => unwrap(await api.get<ResponseModel<TelegramBot[]>>('/sales-bots')) || [],

    create: async (form: TelegramBotForm): Promise<TelegramBot> =>
        unwrap(await api.post<ResponseModel<TelegramBot>>('/sales-bots/manage', form)),

    update: async (id: number, form: Partial<TelegramBotForm> & { unassign?: boolean }): Promise<TelegramBot> =>
        unwrap(await api.put<ResponseModel<TelegramBot>>(`/sales-bots/manage/${id}`, form)),

    remove: async (id: number): Promise<void> => {
        unwrap(await api.delete<ResponseModel<null>>(`/sales-bots/manage/${id}`))
    },

    check: async (id: number): Promise<BotInfo> => unwrap(await api.post<ResponseModel<BotInfo>>(`/sales-bots/manage/${id}/check`)),

    apkInfo: async (): Promise<ApkInfo> => unwrap(await api.get<ResponseModel<ApkInfo>>('/sales-bots/autopay-app/info')),

    apkDownload: async (): Promise<void> => {
        const res = await api.get('/sales-bots/autopay-app/download', { responseType: 'blob' })
        const url = URL.createObjectURL(res.data as Blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'mit-autopay.apk'
        document.body.appendChild(a)
        a.click()
        a.remove()
        setTimeout(() => URL.revokeObjectURL(url), 10_000)
    },

    apkUpload: async (file: File): Promise<ApkInfo> => {
        const fd = new FormData()
        fd.append('file', file)
        return unwrap(
            await api.post<ResponseModel<ApkInfo>>('/sales-bots/autopay-app/upload', fd, {
                headers: { 'Content-Type': 'multipart/form-data' },
            })
        )
    },

    apkFetch: async (): Promise<ApkInfo> => unwrap(await api.post<ResponseModel<ApkInfo>>('/sales-bots/autopay-app/fetch')),

    packs: async (): Promise<EmojiPacks> => unwrap(await api.get<ResponseModel<EmojiPacks>>('/sales-bots/emoji-packs')),
    addPack: async (link: string): Promise<{ packs: EmojiPack[]; pushed: PushResult[]; added: string[]; already: string[] }> =>
        unwrap(
            await api.post<ResponseModel<{ packs: EmojiPack[]; pushed: PushResult[]; added: string[]; already: string[] }>>('/sales-bots/emoji-packs', {
                link,
            })
        ),
    removePack: async (name: string): Promise<{ packs: EmojiPack[]; pushed: PushResult[] }> =>
        unwrap(await api.delete<ResponseModel<{ packs: EmojiPack[]; pushed: PushResult[] }>>(`/sales-bots/emoji-packs/${encodeURIComponent(name)}`)),
    syncPacks: async (): Promise<{ pushed: PushResult[] }> =>
        unwrap(await api.post<ResponseModel<{ pushed: PushResult[] }>>('/sales-bots/emoji-packs/sync')),
}

export interface EmojiPack {
    name: string
    title: string
    emojis: Array<{ id: string; emoji: string }>
}

export interface EmojiPacks {
    configured: boolean
    packs: EmojiPack[]
}

export interface PushResult {
    bot: string
    ok: boolean
    error: string | null
}

export function managementAPI(basePath: string, _kind?: string) {
    return {
        get: async <T = Record<string, unknown>>(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<T> =>
            unwrap(await api.get<ResponseModel<T>>(`${basePath}/${path}`, { params })),
        post: async <T = Record<string, unknown>>(path: string, body: unknown = {}): Promise<T> =>
            unwrap(await api.post<ResponseModel<T>>(`${basePath}/${path}`, body)),
        put: async <T = Record<string, unknown>>(path: string, body: unknown = {}): Promise<T> =>
            unwrap(await api.put<ResponseModel<T>>(`${basePath}/${path}`, body)),
        del: async <T = Record<string, unknown>>(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<T> =>
            unwrap(await api.delete<ResponseModel<T>>(`${basePath}/${path}`, { params })),
        blobURL: async (path: string): Promise<string> => {
            const res = await api.get(`${basePath}/${path}`, { responseType: 'blob' })
            return URL.createObjectURL(res.data as Blob)
        },
    }
}

export function botAPI(botId: number) {
    return managementAPI(`/sales-bots/${botId}/api`)
}

export type BotAPI = ReturnType<typeof botAPI>

// ---------------------------------------------------------------- bot API shapes

export interface BotInfo {
    bot_username: string
    domain: string
    version: string
    role: 'owner' | 'manager'
    admin_id: string
}

export interface BotStats {
    users: number
    blocked_users: number
    wallet_total: number
    active_services: number
    sales_total: number
    sales_24h: number
    sales_24h_amount: number
    test_accounts: number
    panels: number
    pending_payments: number
    paid_total: number
    cancel_requests: number
}

export interface BotPanel {
    id: string
    name_panel: string
    type: string
    status: string
    statusTest: string
    sublink: string
    configManual: string
    onholdstatus: string
    MethodUsername: string
    // owner only
    url_panel?: string
    username_panel?: string
    inboundid?: string
    linksubx?: string
    marzban_url_direct?: string
    marzban_username_direct?: string
    password_set?: boolean
    marzban_password_set?: boolean
}

export interface BotProduct {
    id: string
    code_product: string
    name_product: string
    price_product: string
    Volume_constraint: string
    Location: string
    Service_time: string
    Category: string | null
}

export interface BotCategory {
    id: string
    remark: string
}

export interface BotGiftCode {
    id: string
    code: string
    price: string
    used: number
}

export interface BotDiscount {
    id: string
    codeDiscount: string
    price: string
    limitDiscount: string
    usedDiscount: string
    usefirst: string | null
}

export interface BotHelp {
    id: string
    name_os: string
    Description_os: string
    type_Media_os: string | null
    Media_os: string | null
}

export interface BotUser {
    id: string
    username: string
    number: string
    Balance: string
    User_Status: string
    verify: string
    limit_usertest: string
    affiliatescount: string
    affiliates: string
    last_message_time: string | null
    description_blocking?: string | null
    [k: string]: unknown
}

export interface BotService {
    id_invoice: string
    id_user: string
    username: string
    Service_location: string
    name_product: string
    price_product: string
    Volume: string
    Service_time: string
    time_sell: string
    Status: string
}

export interface BotPayment {
    id: string
    id_user: string
    id_order: string
    time: string
    price: string
    dec_not_confirmed: string | null
    Payment_Method: string
    payment_Status: string
    invoice: string | null
    has_receipt: boolean
    for_purchase: boolean
}

export interface Paged<T> {
    total: number
    items: T[]
}

export interface LabelStyle {
    style?: string
    emoji?: string
}
export interface BotLabelStyles {
    styles: Record<string, LabelStyle>
    suggestions: { categories: string[]; products: string[]; locations: string[]; fixed: string[] }
}

export interface BotButtons {
    mode: 'reply' | 'inline'
    layout: string[][]
    buttons: Record<string, { style?: string; emoji?: string; hidden?: boolean }>
    labels: Record<string, string>
    main_keys: string[]
    extra_keys: string[]
    styles: string[]
}

export interface BotText {
    id: string
    label: string
    button: boolean
    text: string
}

export interface BotSettings {
    Bot_Status: boolean
    roll_Status: boolean
    NotUser: boolean
    help_Status: boolean
    get_number: boolean
    iran_number: boolean
    status_verify: boolean
    statuscategory: boolean
    copy_cart: boolean
    time_usertest: string
    val_usertest: string
    limit_usertest_all: string
    Extra_volume: string
    removedayc: string
    namecustome: string
    Channel_Report: string
    channel: string
    crons: Record<string, boolean>
}

export interface BotPaySettings {
    card_text: string
    nowpayments_key: string
    aqayepardakht_pin: string
    enabled: Record<string, boolean>
}

export interface BotSms {
    id: string
    sender: string
    amount: string | number | null
    sent_at?: string | null
    received_at?: string | null
    status: string
}

export interface BotAutopay {
    mode: 'off' | 'no_review' | 'sms'
    enabled: boolean
    last_seen: string
    device: string
    pairing: string
    endpoint: string
    open_orders: unknown[]
    recent_sms: BotSms[]
    paid_count: number
    open_count: number
    sms_count: number
}

export interface BotAffiliates {
    enabled: boolean
    commission: boolean
    percent: string
    start_gift: boolean
    start_gift_amount: string
    description: string
    has_banner: boolean
}

export interface TopupConnection {
    url: string
    own_key?: boolean
    connected: boolean
    error?: string | null
    bot_username?: string | null
    bot_name?: string | null
}

export const topupConnectionAPI = {
    get: async (): Promise<TopupConnection> => unwrap(await api.get<ResponseModel<TopupConnection>>('/topup-bot/connection')),
    set: async (url: string, key: string): Promise<TopupConnection> =>
        unwrap(await api.put<ResponseModel<TopupConnection>>('/topup-bot/connection', { url, key })),
}

export interface TopupStats {
    configured: boolean
    running: boolean
    users: number
    linked_users: number
    pending_requests: number
    pending_amount: number
    open_bills: number
    open_bills_amount: number
    overdue_bills: number
    overdue_amount: number
    locked_panels: number
    sales_today: number
    sales_today_amount: number
    sales_today_gb: number
}

export interface TopupRequest {
    id: number
    telegram_id: number
    username: string | null
    requested_gb: number
    amount: number
    kind: 'topup' | 'wallet' | 'invoice' | 'settlement' | string
    invoice_id: number | null
    status: string
    created_at: string
    reviewed_at: string | null
    reject_reason: string | null
    has_receipt: boolean
}

export interface TopupSettings {
    price_per_gb: number | null
    card_number: string
    force_join_enabled: boolean
    force_join_channel: string
    auto_approve_enabled: boolean
    has_bulk_pin: boolean
    min_gb: number
    max_gb: number
}

export interface TopupText {
    id: string
    text: string
    default: string
    changed: boolean
    button: boolean
    plain: boolean
    fields: string[]
}

export interface TopupButtons {
    buttons: Record<string, { style: string; emoji: string }>
    labels: Record<string, string>
    defaults: Record<string, string>
    styles: string[]
}

export const topupBotAPI = managementAPI('/topup-bot/api', 'topup')


export interface MaintenanceBot {
    bot_id: number
    bot_name: string
    admin_username: string | null
    enabled: boolean
    eligible: boolean
    next_due_at: string | null
    latest_invoice: {
        invoice_id: number
        status: string
        amount: number
        due_at: string | null
        notified_at: string | null
        last_error: string | null
    } | null
}

export interface MaintenanceOverview {
    eur_price: string
    running: boolean
    bots: MaintenanceBot[]
}

export const maintenanceAPI = {
    get: async (): Promise<MaintenanceOverview> => unwrap(await api.get<ResponseModel<MaintenanceOverview>>('/sales-bots/maintenance')),
    setPrice: async (eur_price: string): Promise<{ eur_price: string }> =>
        unwrap(await api.put<ResponseModel<{ eur_price: string }>>('/sales-bots/maintenance/price', { eur_price })),
    setEnabled: async (id: number, enabled: boolean): Promise<void> => {
        unwrap(await api.put<ResponseModel<null>>(`/sales-bots/maintenance/${id}`, { enabled }))
    },
}
