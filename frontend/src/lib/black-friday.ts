import { useSyncExternalStore } from 'react'
import { settingsAPI, type BrandingInfo } from '@/lib/api'

/**
 * The temporary Black Friday theme. The superadmin switches it on in Settings
 * with an end date; it turns itself off when that moment passes, in the server
 * response and here in the browser, so an open tab drops the theme on time too.
 *
 * The end is remembered in localStorage so index.html can paint the dark theme
 * before React mounts. Without it every load would flash light first.
 */

export interface BlackFriday {
    active: boolean
    endsAt: Date | null
    message: string
}

const STORAGE_KEY = 'bf-until'
const OFF: BlackFriday = { active: false, endsAt: null, message: '' }

let current: BlackFriday = readCached()
let request: Promise<BrandingInfo> | null = null
let expiry = 0
const listeners = new Set<(state: BlackFriday) => void>()

function readCached(): BlackFriday {
    try {
        const until = Number(localStorage.getItem(STORAGE_KEY))
        if (until && until > Date.now()) return { active: true, endsAt: new Date(until), message: '' }
    } catch {
        // Storage blocked: the fetch below decides.
    }
    return OFF
}

function remember(state: BlackFriday) {
    try {
        if (state.active && state.endsAt) localStorage.setItem(STORAGE_KEY, String(state.endsAt.getTime()))
        else localStorage.removeItem(STORAGE_KEY)
    } catch {
        // Only the pre-paint shortcut is lost.
    }
}

function publish(next: BlackFriday) {
    current = next
    remember(next)
    applyClass()
    window.clearTimeout(expiry)
    if (next.active && next.endsAt) {
        // setTimeout caps out near 24.8 days; re-check before that.
        const wait = Math.min(next.endsAt.getTime() - Date.now(), 2 ** 31 - 1)
        expiry = window.setTimeout(() => publish(fromBranding(null)), Math.max(0, wait) + 50)
    }
    listeners.forEach((fn) => fn(next))
}

function fromBranding(branding: BrandingInfo | null): BlackFriday {
    const bf = branding?.black_friday ?? (current.active ? { active: true, ends_at: current.endsAt?.toISOString() ?? null, message: current.message } : null)
    if (!bf?.active || !bf.ends_at) return OFF
    const endsAt = new Date(bf.ends_at)
    if (Number.isNaN(endsAt.getTime()) || endsAt.getTime() <= Date.now()) return OFF
    return { active: true, endsAt, message: bf.message || '' }
}

/** The `bf` class swaps the palette; the panel is dark-only while it is on. */
export function applyClass() {
    const root = document.documentElement
    root.classList.toggle('bf', current.active)
}

/** Re-fetch, e.g. right after the superadmin saves the setting. */
export function refreshBlackFriday(): Promise<BrandingInfo> {
    const pending = settingsAPI.getBranding()
    request = pending
    pending.then((b) => publish(fromBranding(b))).catch(() => { })
    return pending
}

/** The branding response this module already asked for, shared with the login page. */
export function brandingOnce(): Promise<BrandingInfo> {
    return request ?? refreshBlackFriday()
}

function subscribe(listener: () => void) {
    const fn = () => listener()
    listeners.add(fn)
    if (!request) refreshBlackFriday()
    return () => {
        listeners.delete(fn)
    }
}

export function useBlackFriday(): BlackFriday {
    return useSyncExternalStore(subscribe, () => current)
}
