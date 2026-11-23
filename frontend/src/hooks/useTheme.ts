import { useEffect, useState } from 'react'
import { useBlackFriday } from '@/lib/black-friday'

type Theme = 'light' | 'dark'

export function useTheme() {
    const [theme, setTheme] = useState<Theme>(() => {
        // Check localStorage first
        const saved = localStorage.getItem('theme') as Theme | null
        if (saved) return saved

        // Check system preference
        if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
            return 'dark'
        }

        return 'light'
    })

    // The Black Friday theme is dark-only. It overrides the class but not the
    // saved choice, so the user's own theme comes back when the event ends.
    const blackFriday = useBlackFriday().active

    useEffect(() => {
        document.documentElement.classList.toggle('dark', theme === 'dark' || blackFriday)
        localStorage.setItem('theme', theme)
    }, [theme, blackFriday])

    const toggleTheme = () => {
        setTheme((prev) => (prev === 'light' ? 'dark' : 'light'))
    }

    return { theme, toggleTheme, setTheme, locked: blackFriday }
}
