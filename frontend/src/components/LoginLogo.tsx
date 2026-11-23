import { useEffect, useRef, useState } from 'react'
import logoVideo from '@/assets/login-logo.mp4'
import logoPoster from '@/assets/login-logo-poster.webp'

function prefersReducedMotion(): boolean {
    try {
        return window.matchMedia('(prefers-reduced-motion: reduce)').matches
    } catch {
        return false
    }
}

// The animated logo: a muted, looping MP4 rather than a GIF (~87 KB against
// ~1.7 MB for the same clip as a GIF). The poster is the clip's final frame,
// so the complete logo shows before playback starts, when the browser refuses
// autoplay (iOS Low Power Mode, data saver), if the video fails to load, and
// for anyone who asked the OS for reduced motion.
export function LoginLogo({ label, className = 'nx-logo', size = 152 }: { label: string; className?: string; size?: number }) {
    const videoRef = useRef<HTMLVideoElement>(null)
    const [animated, setAnimated] = useState(() => !prefersReducedMotion())

    useEffect(() => {
        const el = videoRef.current
        if (!el) return
        // React sets `muted` as a property only, never as the attribute, and
        // some mobile browsers then treat the video as unmuted and block
        // autoplay. Force it, then ask to play; a refusal just leaves the
        // poster up, so it must not surface as an unhandled rejection.
        el.muted = true
        el.defaultMuted = true
        try {
            const pending = el.play()
            if (pending && typeof pending.catch === 'function') pending.catch(() => { })
        } catch {
            // Very old browsers: autoPlay covers it or the poster stays.
        }
    }, [animated])

    return (
        <div className={className} role="img" aria-label={label}>
            {animated ? (
                <video
                    ref={videoRef}
                    src={logoVideo}
                    poster={logoPoster}
                    width={size}
                    height={size}
                    autoPlay
                    muted
                    loop
                    playsInline
                    preload="auto"
                    disablePictureInPicture
                    disableRemotePlayback
                    tabIndex={-1}
                    aria-hidden="true"
                    onError={() => setAnimated(false)}
                />
            ) : (
                <img src={logoPoster} width={size} height={size} alt="" aria-hidden="true" />
            )}
        </div>
    )
}
