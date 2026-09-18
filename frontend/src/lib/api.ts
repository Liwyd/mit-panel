import { getApiClient } from './api-client'
import { v4 as uuidv4 } from 'uuid'
import {
    LoginResponse,
    DashboardData,
    AdminOutput,
    PanelOutput,
    ClientsOutput,
    ResponseModel,
    AdminFormData,
    PanelFormData,
    MarzbanOverview,
    ServerOutput,
    ServerCreatedOutput,
} from '@/types'


const api = getApiClient()

// Auth API
export const authAPI = {
    login: async (username: string, password: string): Promise<LoginResponse> => {
        const data = new URLSearchParams()
        data.append('username', username)
        data.append('password', password)

        const response = await api.post<ResponseModel<LoginResponse>>(`/login`, data, {
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
        })

        if (!response.data.success) {
            throw new Error(response.data.message || 'Login failed')
        }

        return response.data.data!
    },
}

// Dashboard API
export const dashboardAPI = {
    getDashboardData: async (): Promise<DashboardData> => {
        const response = await api.get<ResponseModel<DashboardData>>(`/dashboard/`)

        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to fetch dashboard data')
        }

        return response.data.data || {}
    },

    getAdmins: async (): Promise<AdminOutput[]> => {
        const response = await api.get<ResponseModel<AdminOutput[]>>(`/superadmin/admins`)

        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to fetch admins')
        }

        return response.data.data || []
    },

    getPanels: async (): Promise<PanelOutput[]> => {
        const response = await api.get<ResponseModel<PanelOutput[]>>(`/superadmin/panels`)

        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to fetch panels')
        }

        return response.data.data || []
    },

    getSystemInfo: async (): Promise<any> => {
        const response = await api.get<ResponseModel<any>>(`/superadmin/system`)

        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to fetch system info')
        }

        return response.data.data || {}
    },

    // Returns null rather than throwing when no Marzban panel is configured or
    // the panel is unreachable, so the dashboard just hides the section.
    getMarzbanOverview: async (
        period: string = '1d',
        force: boolean = false,
        includeAdmins: boolean = false
    ): Promise<MarzbanOverview | null> => {
        const response = await api.get<ResponseModel<MarzbanOverview | null>>(
            `/superadmin/marzban/overview`,
            { params: { period, ...(force ? { refresh: true } : {}), ...(includeAdmins ? { include_admins: true } : {}) } }
        )

        return response.data.data ?? null
    },
}

// Admin API
export const adminAPI = {
    getAdmins: async (): Promise<AdminOutput[]> => {
        const response = await api.get<ResponseModel<AdminOutput[]>>(`/superadmin/admins`)

        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to fetch admins')
        }

        return response.data.data || []
    },

    createAdmin: async (data: AdminFormData): Promise<AdminOutput> => {
        const response = await api.post<ResponseModel<AdminOutput>>(`/superadmin/admin`, data)

        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to create admin')
        }

        return response.data.data!
    },

    updateAdmin: async (adminId: number, data: AdminFormData): Promise<AdminOutput> => {
        const response = await api.put<ResponseModel<AdminOutput>>(
            `/superadmin/admin/${adminId}`,
            data
        )

        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to update admin')
        }

        return response.data.data!
    },

    deleteAdmin: async (adminId: number): Promise<void> => {
        const response = await api.delete<ResponseModel<void>>(
            `/superadmin/admin/${adminId}`
        )

        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to delete admin')
        }
    },

    toggleAdminStatus: async (adminId: number): Promise<AdminOutput> => {
        const response = await api.patch<ResponseModel<AdminOutput>>(
            `/superadmin/admin/${adminId}/status`
        )

        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to toggle admin status')
        }

        return response.data.data!
    },

    getPanelInbounds: async (panelName: string): Promise<Record<string, string[]>> => {
        const response = await api.get<ResponseModel<Record<string, string[]>>>(
            `/superadmin/panel/${panelName}/inbounds`
        )

        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to fetch panel inbounds')
        }

        return response.data.data || {}
    },
}

// Panel API
export const panelAPI = {
    getPanels: async (): Promise<PanelOutput[]> => {
        const response = await api.get<ResponseModel<PanelOutput[]>>(`/superadmin/panels`)

        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to fetch panels')
        }

        return response.data.data || []
    },

    createPanel: async (data: PanelFormData): Promise<PanelOutput> => {
        const response = await api.post<ResponseModel<PanelOutput>>(`/superadmin/panel`, data)

        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to create panel')
        }

        return response.data.data!
    },

    updatePanel: async (panelId: number, data: PanelFormData): Promise<PanelOutput> => {
        const response = await api.put<ResponseModel<PanelOutput>>(
            `/superadmin/panel/${panelId}`,
            data
        )

        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to update panel')
        }

        return response.data.data!
    },

    deletePanel: async (panelId: number): Promise<void> => {
        const response = await api.delete<ResponseModel<void>>(
            `/superadmin/panel/${panelId}`
        )

        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to delete panel')
        }
    },

    togglePanelStatus: async (panelId: number): Promise<PanelOutput> => {
        const response = await api.patch<ResponseModel<PanelOutput>>(
            `/superadmin/panel/${panelId}/status`
        )

        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to toggle panel status')
        }

        return response.data.data!
    },
}

// SuperAdmin API
export const superadminAPI = {
    downloadBackup: async (): Promise<Blob> => {
        const response = await api.get(`/superadmin/backup`, {
            responseType: 'blob',
        })
        return response.data
    },

    restoreBackup: async (file: File): Promise<string> => {
        const formData = new FormData()
        formData.append('file', file)

        const response = await api.post<ResponseModel<void>>(`/superadmin/restore`, formData, {
            headers: {
                'Content-Type': 'multipart/form-data',
            },
        })

        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to restore backup')
        }

        return response.data.message || 'Database restored successfully'
    },

    getLogs: async (): Promise<string[]> => {
        const response = await api.get<ResponseModel<string[]>>(`/superadmin/logs`)

        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to fetch logs')
        }

        return response.data.data || []
    },

    getNews: async (): Promise<Array<{ id: number; message: string | null; created_at: string; has_banner: boolean }>> => {
        const response = await api.get<ResponseModel<Array<{ id: number; message: string | null; created_at: string; has_banner: boolean }>>>(`/superadmin/news`)

        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to fetch news')
        }

        return response.data.data || []
    },

    addNews: async (message: string, image?: File | null): Promise<void> => {
        const formData = new FormData()
        if (message) formData.append('message', message)
        if (image) formData.append('image', image)

        const response = await api.post<ResponseModel<void>>(`/superadmin/news`, formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
        })

        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to add news')
        }
    },

    deleteNews: async (newsId: number): Promise<void> => {
        const response = await api.delete<ResponseModel<void>>(`/superadmin/news/${newsId}`)

        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to delete news')
        }
    },
}

// Helper function to generate random sub_id (16 random characters)
function generateSubId(): string {
    const chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    const bytes = crypto.getRandomValues(new Uint8Array(16))
    let result = ''
    for (const b of bytes) {
        result += chars[b % chars.length]
    }
    return result
}

// Resolve an expiry value into the epoch-ms timestamp the backend expects.
// A number is an exact timestamp and is passed through untouched, so operations
// that only mean to change something else (enable/disable, traffic, ...) never
// shift the expiry. A "YYYY-MM-DD" string is anchored to local midnight.
function toExpiryTimestamp(expiryDatetime: string | number | null | undefined): number {
    if (expiryDatetime === null || expiryDatetime === undefined || expiryDatetime === '') {
        return 0
    }
    if (typeof expiryDatetime === 'number') {
        return Number.isFinite(expiryDatetime) ? Math.floor(expiryDatetime) : 0
    }
    return new Date(expiryDatetime + 'T00:00:00').getTime()
}

// User API
export const userAPI = {
    createUser: async (email: string, totalGb: number, expiryDatetime?: string | number | null): Promise<ClientsOutput> => {
        const submitData = {
            email,
            id: uuidv4(),
            enable: true,
            expiry_time: toExpiryTimestamp(expiryDatetime),
            total: Math.round(totalGb * 1024 * 1024 * 1024),
            sub_id: generateSubId(),
            flow: '',
        }

        const response = await api.post<ResponseModel<ClientsOutput>>(`/admin/user`, submitData)

        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to create user')
        }

        return response.data.data!
    },

    updateUser: async (
        userUuid: string,
        email: string,
        totalGb: number,
        expiryDatetime: string | number | null | undefined,
        subId: string,
        enable: boolean = true,
        flow: string = '',
        userId?: string
    ): Promise<ClientsOutput> => {
        // Sanitize sub_id to remove leading and trailing slashes to prevent double slashes in subscription URL
        const sanitizedSubId = subId?.replace(/^\/+|\/+$/g, '') || '';

        const submitData = {
            email,
            enable,
            expiry_time: toExpiryTimestamp(expiryDatetime),
            total: Math.round(totalGb * 1024 * 1024 * 1024),
            sub_id: sanitizedSubId,
            flow,
        }

        const identifier = (userUuid && userUuid !== '0') ? userUuid : (userId || '0')

        const response = await api.put<ResponseModel<ClientsOutput>>(
            `/admin/user/${identifier}`,
            submitData
        )

        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to update user')
        }

        return response.data.data!
    },

    deleteUser: async (userUuid: string, username?: string, userId?: string): Promise<void> => {
        // Use userUuid if available (could be uuid or username), otherwise use username, then userId
        const identifier = (userUuid && userUuid !== '0')
            ? userUuid
            : (username || userId || '0')

        const response = await api.delete<ResponseModel<void>>(
            `/admin/user/${identifier}`
        )

        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to delete user')
        }
    },

    toggleUserStatus: async (userUuid: string): Promise<ClientsOutput> => {
        const response = await api.patch<ResponseModel<ClientsOutput>>(
            `/admin/user/${userUuid}/status`
        )

        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to toggle user status')
        }

        return response.data.data!
    },

    resetUserUsage: async (email: string): Promise<void> => {
        const response = await api.put<ResponseModel<void>>(
            `/admin/user/${email}/reset`
        )

        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to reset user usage')
        }
    },
}

// Settings API
export interface PanelSettings {
    login_title: string
    telegram_bot_token: string
    telegram_chat_id: string
    backup_enabled: boolean
    backup_interval_hours: number
    has_logo: boolean
    bot_enabled: boolean
    bot_token: string
    bot_superadmin_ids: string
    bot_media_dir: string
    bot_min_gb: number
    bot_max_gb: number
}

export interface BrandingInfo {
    login_title: string
    has_logo: boolean
}

export function getLogoUrl(bust = false): string {
    const prefix = import.meta.env.VITE_URL_PREFIX || 'dashboard'
    const base = `/${prefix}/dashboard/logo`
    return bust ? `${base}?t=${Date.now()}` : base
}

export const settingsAPI = {
    getBranding: async (): Promise<BrandingInfo> => {
        const response = await api.get<ResponseModel<BrandingInfo>>(`/dashboard/branding`)
        return response.data.data || { login_title: 'MIT Panel', has_logo: false }
    },

    getSettings: async (): Promise<PanelSettings> => {
        const response = await api.get<ResponseModel<PanelSettings>>(`/superadmin/settings`)
        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to fetch settings')
        }
        return response.data.data!
    },

    updateSettings: async (data: Partial<PanelSettings>): Promise<PanelSettings> => {
        const response = await api.put<ResponseModel<PanelSettings>>(`/superadmin/settings`, data)
        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to update settings')
        }
        return response.data.data!
    },

    uploadLogo: async (file: File): Promise<void> => {
        const formData = new FormData()
        formData.append('file', file)
        const response = await api.post<ResponseModel<void>>(`/superadmin/settings/logo`, formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
        })
        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to upload logo')
        }
    },

    testTelegram: async (): Promise<string> => {
        const response = await api.post<ResponseModel<void>>(`/superadmin/settings/telegram/test`)
        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to send test backup')
        }
        return response.data.message || 'Test backup sent'
    },

    getBotSettings: async (): Promise<PanelSettings> => {
        const response = await api.get<ResponseModel<PanelSettings>>(`/superadmin/settings/bot`)
        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to fetch bot settings')
        }
        return response.data.data!
    },

    updateBotSettings: async (data: Partial<PanelSettings>): Promise<PanelSettings> => {
        const response = await api.put<ResponseModel<PanelSettings>>(`/superadmin/settings/bot`, data)
        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to update bot settings')
        }
        return response.data.data!
    },

    getVersion: async (): Promise<{ version: string }> => {
        const response = await api.get<ResponseModel<{ version: string }>>(`/dashboard/version`)
        return response.data.data || { version: 'unknown' }
    },
}

// Server API
export const serverAPI = {
    getServers: async (): Promise<ServerOutput[]> => {
        const response = await api.get<ResponseModel<ServerOutput[]>>(`/superadmin/servers`)
        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to fetch servers')
        }
        return response.data.data || []
    },

    createServer: async (name: string): Promise<ServerCreatedOutput> => {
        const response = await api.post<ResponseModel<ServerCreatedOutput>>(`/superadmin/servers`, { name })
        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to create server')
        }
        return response.data.data!
    },

    renameServer: async (serverId: number, name: string): Promise<void> => {
        const response = await api.put<ResponseModel<void>>(`/superadmin/servers/${serverId}`, { name })
        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to rename server')
        }
    },

    deleteServer: async (serverId: number): Promise<void> => {
        const response = await api.delete<ResponseModel<void>>(`/superadmin/servers/${serverId}`)
        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to delete server')
        }
    },

    rebootServer: async (serverId: number): Promise<void> => {
        const response = await api.post<ResponseModel<void>>(`/superadmin/servers/${serverId}/reboot`)
        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to reboot server')
        }
    },

    reorderServers: async (orderedIds: number[]): Promise<void> => {
        const response = await api.put<ResponseModel<void>>(`/superadmin/servers/reorder`, { ordered_ids: orderedIds })
        if (!response.data.success) {
            throw new Error(response.data.message || 'Failed to reorder servers')
        }
    },
}
