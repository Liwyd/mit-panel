import { useEffect, useState } from 'react'
import { BotAPI } from '@/lib/bots-api'
import { cn } from '@/lib/utils'

// Still previews of premium (custom) emoji, fetched once per id through the
// bot (Telegram serves them only to bots) and kept for the page's lifetime.
const cache = new Map<string, Promise<string | null>>()

function previewURL(api: BotAPI, botKey: string, id: string): Promise<string | null> {
    const k = `${botKey}:${id}`
    let p = cache.get(k)
    if (!p) {
        p = api.blobURL(`emoji/${id}`).catch(() => null)
        cache.set(k, p)
    }
    return p
}

export function PremiumEmoji({
    api,
    botKey,
    id,
    fallback = '✦',
    className,
}: {
    api: BotAPI
    botKey: string
    id: string | undefined
    fallback?: string
    className?: string
}) {
    const [state, setState] = useState<{ id: string; url: string | null } | null>(null)
    useEffect(() => {
        if (!id) return
        let live = true
        previewURL(api, botKey, id).then((url) => live && setState({ id, url }))
        return () => {
            live = false
        }
    }, [api, botKey, id])
    if (!id) return null
    const url = state?.id === id ? state.url : null
    return url ? (
        <img
            src={url}
            alt=""
            draggable={false}
            onError={() => setState({ id, url: null })}
            className={cn('inline-block h-[1.15em] w-[1.15em] object-contain align-[-0.2em]', className)}
        />
    ) : (
        <span className={cn('inline-block w-[1.15em] text-center', className)}>{fallback}</span>
    )
}
