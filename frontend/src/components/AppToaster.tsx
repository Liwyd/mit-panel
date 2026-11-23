import { useEffect, useState } from 'react'
import { Toaster } from 'sonner'

const readTheme = (): 'dark' | 'light' =>
    document.documentElement.classList.contains('dark') ? 'dark' : 'light'

/** Single app-wide toast host; its theme follows the `dark` class on <html>. */
export function AppToaster() {
    const [theme, setTheme] = useState<'dark' | 'light'>(readTheme)

    useEffect(() => {
        const observer = new MutationObserver(() => setTheme(readTheme()))
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
        return () => observer.disconnect()
    }, [])

    return (
        <Toaster
            position="top-center"
            closeButton
            duration={4000}
            theme={theme}
            toastOptions={{
                classNames: {
                    toast: 'bg-card text-card-foreground border border-border shadow-lg rounded-xl font-sans',
                    description: 'text-muted-foreground',
                },
            }}
        />
    )
}
