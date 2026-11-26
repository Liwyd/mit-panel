import { z } from 'zod'

const USERNAME_REGEX = /^[a-zA-Z0-9][a-zA-Z0-9_.\-]*$/
const USERNAME_RULE = 'Only letters, numbers, underscores, dots and hyphens. Must start with a letter or number.'

// Auth Types
export interface DecodedToken {
    sub: string
    role: 'admin' | 'superadmin'
    panel: string
    exp: number
}

// Login Form
export const loginSchema = z.object({
    username: z
        .string()
        .min(1, 'Username is required')
        .min(3, 'Username must be at least 3 characters')
        .max(50, 'Username must be less than 50 characters')
        .regex(USERNAME_REGEX, USERNAME_RULE),
    password: z
        .string()
        .min(1, 'Password is required')
        .min(4, 'Password must be at least 4 characters')
        .max(100, 'Password must be less than 100 characters'),
})

export type LoginFormData = z.infer<typeof loginSchema>

// Admin Form
export const adminSchema = z.object({
    username: z
        .string()
        .min(1, 'Username is required')
        .min(3, 'Username must be at least 3 characters')
        .max(50, 'Username must be less than 50 characters')
        .regex(USERNAME_REGEX, USERNAME_RULE),

    password: z.string()
    .optional()
    .refine(
        (val) => val === undefined || val === '' || val.length >= 4,
        { message: "Password must be at least 4 characters" }
    )
    .refine(
        (val) => val === undefined || val === '' || val.length <= 100,
        { message: "Password must be less than 100 characters" }
    ),

    panel: z
        .string()
        .min(1, 'Panel selection is required'),

    inbound_id: z
        .string()
        .regex(
            /^(\d+(,\d+)*)?$/,
            'Inbound IDs must be like: 1,2,3'
        )
        .optional()
        .nullable(),

    marzban_inbounds: z
        .string()
        .optional()
        .nullable(),

    marzban_all_inbounds: z
        .boolean()
        .default(false),

    marzban_password: z
        .string()
        .optional()
        .nullable(),

    flow: z
        .string()
        .optional()
        .nullable(),

    traffic: z
        .number()
        .min(0, 'Traffic cannot be negative')
        .default(0),

    initial_traffic: z
        .number()
        .min(0, 'Total quota cannot be negative')
        .optional(),

    update_return_traffic: z
        .boolean()
        .default(false),

    delete_return_traffic: z
        .boolean()
        .default(false),

    is_active: z
        .boolean()
        .default(true),

    expiry_date: z
        .union([z.string(), z.number()])
        .nullable()
        .optional(),

    telegram_id: z
        .union([z.number(), z.null()])
        .optional(),
})
    .superRefine((val, ctx) => {
        // If panel is 3x-ui, flow must be provided (not null/empty)
        if (val.panel === '3x-ui') {
            const f = val.flow
            if (f === null || f === undefined || String(f).trim() === '') {
                ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'Flow is required for 3x-ui panels', path: ['flow'] })
            }
        }
    })

export type AdminFormData = z.infer<typeof adminSchema>

export interface AdminOutput {
    id: number
    username: string
    is_active: boolean
    panel: string
    inbound_id: string | null
    marzban_inbounds: string | null
    marzban_all_inbounds?: boolean
    marzban_password: string | null
    flow?: string | null
    traffic: number
    initial_traffic: number
    update_return_traffic: boolean | false
    delete_return_traffic: boolean | false
    expiry_date: string | null
    telegram_id?: number | null
    /** Why the bot locked this admin's login; null/absent when not locked. */
    suspended_reason?: string | null
    /** «ادمین ویژه»: billed for real usage instead of a prepaid balance. */
    metered?: boolean
}

// Panel Form
export const panelSchema = z.object({
    panel_type: z
        .string()
        .min(1, 'Panel type is required')
        .default('3x-ui'),

    name: z
        .string()
        .min(1, 'Panel name is required')
        .min(3, 'Panel name must be at least 3 characters')
        .max(100, 'Panel name must be less than 100 characters'),

    url: z
        .string()
        .min(1, 'Panel URL is required')
        .url('Must be a valid URL')
        .max(500, 'URL must be less than 500 characters'),

    sub_url: z
        .string()
        .url('Must be a valid URL if provided')
        .nullable()
        .optional(),

    username: z
        .string()
        .min(1, 'Username is required')
        .min(3, 'Username must be at least 3 characters')
        .max(50, 'Username must be less than 50 characters')
        .regex(USERNAME_REGEX, USERNAME_RULE),

    password: z
        .string()
        .min(1, 'Password is required')
        .min(4, 'Password must be at least 4 characters')
        .max(100, 'Password must be less than 100 characters'),

    token: z
        .string()
        .optional()
        .nullable(),

    is_active: z
        .boolean()
        .default(true),
})

    .superRefine((val, ctx) => {
        if (val.panel_type === '3x-ui' || val.panel_type === 'guard') {
            const token = val.token
            if (token === undefined || token === null || String(token).trim() === '') {
                ctx.addIssue({
                    code: z.ZodIssueCode.custom,
                    message: 'Token is required for 3x-ui or guard panels',
                    path: ['token'],
                })
            } else if (typeof token === 'string' && token.length > 500) {
                ctx.addIssue({
                    code: z.ZodIssueCode.custom,
                    message: 'Token must be less than 500 characters',
                    path: ['token'],
                })
            }
        }
    })

export type PanelFormData = z.infer<typeof panelSchema>

export interface PanelOutput {
    id: number
    panel_type: string
    name: string
    url: string
    is_active: boolean
}

export type ServerStatus = 'connected' | 'connecting' | 'disconnected'

export interface ServerOutput {
    id: number
    name: string
    status: ServerStatus
    last_seen_at: string | null
    cpu_percent: number | null
    cpu_cores: number | null
    ram_used: number | null
    ram_total: number | null
    swap_used: number | null
    swap_total: number | null
    disk_used: number | null
    disk_total: number | null
}

export interface ServerCreatedOutput {
    id: number
    name: string
    token: string
}

// User Form
export const userSchema = z.object({
    email: z
        .string()
        .min(1, 'Username/Email is required')
        .max(100, 'Maximum 100 characters')
        .regex(USERNAME_REGEX, USERNAME_RULE),

    totalGb: z
        .number()
        .min(0.1, 'Minimum traffic is 0.1 GB')
        .max(109951.16, 'Maximum traffic is ~107 TB'),

    expiryDatetime: z
        .union([z.string(), z.number()])
        .optional()
        .nullable(),
})

export type UserFormData = z.infer<typeof userSchema>

export interface ClientsOutput {
    id: number
    uuid: string
    username: string
    status: boolean
    is_online: boolean
    online_at?: string | null
    data_limit: number
    used_data: number
    expiry_date: string | null
    expiry_date_unix: number | null
    sub_id?: string
    flow?: string
}

// API Response Types
export interface ResponseModel<T = any> {
    success: boolean
    message: string
    data?: T
}

export interface LoginResponse {
    access_token: string
    token_type: string
}

export interface SystemInfo {
    total_memory: number
    used_memory: number
    cpu_percent: number
    cpu_cores?: number
    disk_total: number
    disk_used: number
    swap_total?: number
    swap_used?: number
}

export type MarzbanNodeStatus = 'connected' | 'connecting' | 'error' | 'disabled' | 'unknown'

export interface MarzbanNodeUsage {
    id: number | null
    name: string
    usage: number
    status: MarzbanNodeStatus
}

export interface MarzbanOverview {
    panel: string
    period: string
    version?: string | null
    users: {
        active: number
        total: number
        /** null when the online scan failed; the rest of the payload is still valid. */
        online: number | null
    }
    traffic: {
        incoming: number
        outgoing: number
        total: number
    }
    memory: {
        used: number
        total: number
    }
    cpu: {
        usage: number
        cores: number
    }
    nodes: {
        total: number
        items: MarzbanNodeUsage[]
    }
    admins?: {
        mit: number
        marzban_only: number
    } | null
}

export const MARZBAN_PERIODS = ['1h', '7h', '1d', '3d', '1w', '1m', '3m'] as const
export type MarzbanPeriod = typeof MARZBAN_PERIODS[number]

export interface NewsFeedItem {
    id: number
    message: string | null
    has_banner: boolean
}

/** «ادمین ویژه»: billed for real usage (backend/bot/metering.py). GB only. */
export interface MeteredUsage {
    since: string | null
    used_bytes: number
    unsettled_bytes: number
    prepaid_bytes: number
    read_at: string | null
}

export interface DashboardData {
    can_revoke_subscription?: boolean
    metered?: MeteredUsage
    remaining_traffic?: number
    initial_traffic?: number
    expiry_time?: string
    news?: NewsFeedItem[]
    sub_url?: string
    users?: ClientsOutput[]
    admins?: AdminOutput[]
    panels?: PanelOutput[]
    system?: SystemInfo
}

/** The node-ranking window the Analytics page offers. */
export type AnalyticsNodePeriod = '1d' | '7d' | '30d'

/** What GET /admin/analytics returns (backend/utils/analytics.py). */
export interface AdminAnalytics {
    generated_at: string
    utc_offset_minutes: number
    remaining: number
    initial: number
    usage: {
        today: number
        yesterday: number
        /** Last 24 local hours, oldest first; `label` is the local "HH:00". */
        hourly: { start: string; label: string; used: number }[]
        /** Last 7 local days, oldest first, today last. */
        daily: { start: string; date: string; used: number }[]
        /** When usage started being recorded, null before the first reading. */
        since: string | null
    }
    sales: {
        daily: { start: string; date: string; sold: number }[]
        window_days: number
        window_total: number
        per_day: number
        /** Sales of the last `tomorrow_window_hours`, as tomorrow's forecast. */
        tomorrow: number
        tomorrow_window_hours: number
        /** null when nothing was sold lately (the balance isn't running down). */
        days_left: number | null
        runs_out_at: string | null
        days_covered: number
    }
    nodes: {
        period: AnalyticsNodePeriod
        /** null when Marzban couldn't be read. */
        items: { id: number | null; name: string; used: number }[] | null
        total: number
    }
}

/** One Marzban panel's nodes and the custom names set for them. */
export interface NodeNamesPanel {
    panel_id: number
    panel_name: string
    /** false when the node list couldn't be read from Marzban. */
    reachable: boolean
    /** key is Marzban's node id, or "master"; name is '' when not renamed. */
    nodes: { key: string; marzban_name: string; name: string }[]
}
