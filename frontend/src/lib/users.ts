/** Helpers shared by the dashboard and its user list. */

export function buildSubUrl(subUrl?: string, subId?: string) {
    if (!subUrl || !subId) return ''

    if (subId.startsWith('http://') || subId.startsWith('https://')) {
        return subId
    }

    const cleanBase = subUrl.replace(/\/+$/, '')
    const cleanId = subId.replace(/^\/+/, '')

    return `${cleanBase}/${cleanId}`
}

export function lastOnlineInfo(onlineAt?: string | null): { online: boolean; text: string } {
    if (!onlineAt) return { online: false, text: 'Never online' }
    const iso = /[zZ]|[+-]\d\d:?\d\d$/.test(onlineAt) ? onlineAt : onlineAt + 'Z'
    const t = new Date(iso).getTime()
    if (isNaN(t)) return { online: false, text: '—' }
    const diff = Date.now() - t
    if (diff < 60000) return { online: true, text: 'Online' }
    const m = Math.floor(diff / 60000)
    if (m < 60) return { online: false, text: `${m}m ago` }
    const h = Math.floor(m / 60)
    if (h < 24) return { online: false, text: `${h}h ago` }
    const d = Math.floor(h / 24)
    return { online: false, text: `${d}d ago` }
}
