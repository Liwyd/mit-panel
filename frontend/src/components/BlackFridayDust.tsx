import { useEffect, useRef } from 'react'
import { useBlackFriday } from '@/lib/black-friday'

/*
 * Drifting red embers for the Black Friday theme. Purely decorative.
 *
 * Cost control: every colour x size bucket is drawn once to an offscreen
 * canvas and the frame only blits those sprites, at 30fps at most, with the
 * pixel ratio capped at 2. The loop stops in hidden tabs, and reduced motion
 * gets a single still frame.
 *
 * 'panel' sits behind the content (z-index -1 inside the isolated Layout root,
 * so it paints over the root background but under the sidebar and cards).
 * 'login' drifts over the price tag but under the form, thinner than the panel's.
 */

// Hex only: canvas colour parsing on older browsers rejects CSS Color 4 syntax.
// #e67070 is the panel coral, hsl(0 70% 67%).
const COLORS = ['#ff3b2f', '#e67070', '#d9241c']
const SPARK_BUCKETS = [1, 1.6, 2.4]
const BOKEH_BUCKETS = [4, 6]
const FRAME_MS = 1000 / 30

interface Particle {
    x: number
    y: number
    r: number
    sprite: number
    alpha: number
    speed: number
    freq: number
    phase: number
    amp: number
    twFreq: number
    twPhase: number
    bokeh: boolean
}

interface Sprite {
    canvas: HTMLCanvasElement
}

const rand = (a: number, b: number) => a + Math.random() * (b - a)
const SIZES = [...SPARK_BUCKETS, ...BOKEH_BUCKETS]

function makeSprites(dpr: number): Sprite[] {
    const sprites: Sprite[] = []
    for (const color of COLORS) {
        for (const r of SIZES) {
            const size = Math.max(2, Math.ceil(r * 2 * dpr))
            const c = document.createElement('canvas')
            c.width = c.height = size
            const g = c.getContext('2d')
            if (g) {
                const grad = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
                grad.addColorStop(0, color)
                grad.addColorStop(0.45, color)
                grad.addColorStop(1, 'rgba(0,0,0,0)')
                g.fillStyle = grad
                g.fillRect(0, 0, size, size)
            }
            sprites.push({ canvas: c })
        }
    }
    return sprites
}

function spriteIndex(color: number, r: number, bokeh: boolean) {
    const buckets = bokeh ? BOKEH_BUCKETS : SPARK_BUCKETS
    let best = 0
    buckets.forEach((b, i) => {
        if (Math.abs(b - r) < Math.abs(buckets[best] - r)) best = i
    })
    return color * SIZES.length + (bokeh ? SPARK_BUCKETS.length : 0) + best
}

function spawn(width: number, height: number, maxAlpha: number, anywhere: boolean): Particle {
    const bokeh = Math.random() < 0.1
    const r = bokeh ? rand(3.5, 6) : rand(0.9, 2.4)
    const color = Math.floor(Math.random() * COLORS.length)
    return {
        x: rand(0, width),
        y: anywhere ? rand(0, height) : height + rand(0, 20),
        r,
        sprite: spriteIndex(color, r, bokeh),
        alpha: bokeh ? rand(0.08, 0.2) : rand(0.3, maxAlpha),
        speed: rand(6, 18),
        freq: rand(0.2, 0.7),
        phase: rand(0, Math.PI * 2),
        amp: rand(4, 14),
        twFreq: (Math.PI * 2) / rand(3, 7),
        twPhase: rand(0, Math.PI * 2),
        bokeh,
    }
}

export function BlackFridayDust({ variant }: { variant: 'panel' | 'login' }) {
    const { active } = useBlackFriday()
    const ref = useRef<HTMLCanvasElement>(null)

    useEffect(() => {
        const canvas = ref.current
        if (!active || !canvas) return
        let ctx: CanvasRenderingContext2D | null = null
        try {
            ctx = canvas.getContext('2d')
        } catch {
            return
        }
        if (!ctx) return

        const login = variant === 'login'
        const maxAlpha = login ? 0.6 : 0.8
        const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
        let sprites: Sprite[] = []
        let dpr = 0
        let width = 0
        let height = 0
        const particles: Particle[] = []
        let raf = 0
        let last = 0
        let time = 0

        const targetCount = () => {
            const base = Math.min(100, Math.max(28, Math.round((width * height) / 15000)))
            return login ? Math.round(base * 0.6) : base
        }

        const draw = () => {
            ctx.clearRect(0, 0, width, height)
            for (const p of particles) {
                const twinkle = 1 + 0.35 * Math.sin(time * p.twFreq + p.twPhase)
                ctx.globalAlpha = Math.min(1, Math.max(0, p.alpha * twinkle))
                const x = p.x + Math.sin(time * p.freq + p.phase) * p.amp
                ctx.drawImage(sprites[p.sprite].canvas, x - p.r, p.y - p.r, p.r * 2, p.r * 2)
            }
            ctx.globalAlpha = 1
        }

        const resize = () => {
            const w = canvas.clientWidth
            const h = canvas.clientHeight
            if (!w || !h) return
            const nextDpr = Math.min(2, window.devicePixelRatio || 1)
            if (nextDpr !== dpr) {
                dpr = nextDpr
                sprites = makeSprites(dpr)
            }
            const oldW = width
            const oldH = height
            width = w
            height = h
            canvas.width = Math.round(w * dpr)
            canvas.height = Math.round(h * dpr)
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
            // Keep the particles, scaled to the new box; add or drop to the new count.
            if (oldW && oldH) {
                for (const p of particles) {
                    p.x *= w / oldW
                    p.y *= h / oldH
                }
            }
            const count = targetCount()
            if (particles.length > count) particles.length = count
            while (particles.length < count) particles.push(spawn(width, height, maxAlpha, true))
            if (reduced) draw()
        }

        const frame = (ts: number) => {
            raf = requestAnimationFrame(frame)
            try {
                step(ts)
            } catch {
                // Never let a drawing error repeat every frame.
                stop()
            }
        }

        const step = (ts: number) => {
            if (ts - last < FRAME_MS) return
            const dt = last ? Math.min(0.1, (ts - last) / 1000) : 0
            last = ts
            time += dt
            for (const p of particles) {
                p.y -= p.speed * dt
                if (p.y < -10) {
                    const fresh = spawn(width, height, maxAlpha, false)
                    Object.assign(p, fresh)
                }
            }
            draw()
        }

        const start = () => {
            if (raf || reduced || document.hidden) return
            last = 0
            raf = requestAnimationFrame(frame)
        }
        const stop = () => {
            cancelAnimationFrame(raf)
            raf = 0
        }
        const onVisibility = () => (document.hidden ? stop() : start())

        try {
            resize()
        } catch {
            // Decoration only: no canvas support worth having, so stay blank.
            return
        }
        const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(resize)
        observer?.observe(canvas)
        window.addEventListener('resize', resize)
        document.addEventListener('visibilitychange', onVisibility)
        start()

        return () => {
            stop()
            observer?.disconnect()
            window.removeEventListener('resize', resize)
            document.removeEventListener('visibilitychange', onVisibility)
        }
    }, [active, variant])

    if (!active) return null

    const style: React.CSSProperties =
        variant === 'panel'
            ? { position: 'fixed', inset: 0, zIndex: -1, width: '100%', height: '100%', pointerEvents: 'none' }
            : { position: 'absolute', inset: 0, zIndex: 1, width: '100%', height: '100%', pointerEvents: 'none' }

    return <canvas ref={ref} aria-hidden="true" style={style} />
}
