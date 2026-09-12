import { useEffect, useState } from 'react'
import { getApiClient } from '@/lib/api-client'

const cache = new Map<number, string>()
const inFlight = new Map<number, Promise<string>>()

async function fetchBannerUrl(newsId: number): Promise<string> {
    const cached = cache.get(newsId)
    if (cached) return cached

    const pending = inFlight.get(newsId)
    if (pending) return pending

    const promise = getApiClient()
        .get(`/dashboard/banner/${newsId}`, { responseType: 'blob' })
        .then((res) => {
            const url = URL.createObjectURL(res.data)
            cache.set(newsId, url)
            inFlight.delete(newsId)
            return url
        })
        .catch((err) => {
            inFlight.delete(newsId)
            throw err
        })

    inFlight.set(newsId, promise)
    return promise
}

export function useBannerImage(newsId: number, hasBanner: boolean): string | null {
    const [url, setUrl] = useState<string | null>(() => {
        if (!hasBanner) return null
        return cache.get(newsId) || null
    })

    useEffect(() => {
        if (!hasBanner) return

        let cancelled = false
        fetchBannerUrl(newsId)
            .then((resolved) => {
                if (!cancelled) setUrl(resolved)
            })
            .catch(() => {
                if (!cancelled) setUrl(null)
            })

        return () => {
            cancelled = true
        }
    }, [newsId, hasBanner])

    return hasBanner ? url : null
}
