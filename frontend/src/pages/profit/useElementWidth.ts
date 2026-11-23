import { useEffect, useState, type RefObject } from 'react'

/** The rendered width of an element, kept current with a ResizeObserver. */
export function useElementWidth(ref: RefObject<HTMLElement>, fallback = 600): number {
    const [width, setWidth] = useState(fallback)
    useEffect(() => {
        const element = ref.current
        if (!element) return
        const read = () => setWidth(Math.max(1, Math.round(element.getBoundingClientRect().width)))
        read()
        const observer = new ResizeObserver(read)
        observer.observe(element)
        return () => observer.disconnect()
    }, [ref])
    return width
}
