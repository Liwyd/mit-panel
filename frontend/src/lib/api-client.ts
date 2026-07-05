import axios, { AxiosInstance, AxiosError } from 'axios'
import { getToken, removeToken } from './auth'
import { formatApiError } from './errors'

let apiClient: AxiosInstance | null = null

function getBaseURL(): string {
    // URL_PREFIX is configurable (e.g., "dashboard" from .env)
    // Final URL structure: {host}/{URL_PREFIX}/{endpoint}
    const urlPrefix = import.meta.env.VITE_URL_PREFIX || 'dashboard'

    // For production: use current host
    if (import.meta.env.MODE === 'production') {
        const protocol = window.location.protocol
        const host = window.location.host
        return `${protocol}//${host}/${urlPrefix}`
    }

    // For development: use environment variable or default
    const apiBaseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
    return `${apiBaseURL}/${urlPrefix}`
} export function initializeApiClient(): AxiosInstance {
    if (apiClient) return apiClient

    apiClient = axios.create({
        baseURL: getBaseURL(),
        headers: {
            'Content-Type': 'application/json',
        },
    })

    // Request interceptor
    apiClient.interceptors.request.use(
        (config) => {
            const token = getToken()
            if (token) {
                config.headers.Authorization = `Bearer ${token}`
            }
            return config
        },
        (error) => {
            return Promise.reject(error)
        }
    )

    // Response interceptor
    apiClient.interceptors.response.use(
        (response) => response,
        (error: AxiosError) => {
            // Handle 401 Unauthorized — but NOT for the login request itself,
            // so the login page can show "wrong username/password" inline.
            if (error.response?.status === 401) {
                const reqUrl = error.config?.url || ''
                if (!reqUrl.includes('/login')) {
                    removeToken()
                    const prefix = import.meta.env.VITE_URL_PREFIX || 'dashboard'
                    window.location.href = `/${prefix}/login`
                }
            }
            // Surface a human-readable "Error <code> — <reason>" everywhere
            error.message = formatApiError(error)
            return Promise.reject(error)
        }
    )

    return apiClient
}

export function getApiClient(): AxiosInstance {
    if (!apiClient) {
        initializeApiClient()
    }
    return apiClient!
}
