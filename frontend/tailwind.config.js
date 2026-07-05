/** @type {import('tailwindcss').Config} */
export default {
    darkMode: ['class'],
    content: [
        './index.html',
        './src/**/*.{js,ts,jsx,tsx}',
    ],
    theme: {
        extend: {
            fontFamily: {
                rubik: ['Rubik', 'sans-serif'],
                bangers: ['Bangers', 'cursive'],
            },
            colors: {
                border: 'hsl(var(--border))',
                input: 'hsl(var(--input))',
                ring: 'hsl(var(--ring))',
                background: 'hsl(var(--background))',
                foreground: 'hsl(var(--foreground))',
                primary: {
                    DEFAULT: 'hsl(var(--primary))',
                    foreground: 'hsl(var(--primary-foreground))',
                },
                secondary: {
                    DEFAULT: 'hsl(var(--secondary))',
                    foreground: 'hsl(var(--secondary-foreground))',
                },
                destructive: {
                    DEFAULT: 'hsl(var(--destructive))',
                    foreground: 'hsl(var(--destructive-foreground))',
                },
                muted: {
                    DEFAULT: 'hsl(var(--muted))',
                    foreground: 'hsl(var(--muted-foreground))',
                },
                accent: {
                    DEFAULT: 'hsl(var(--accent))',
                    foreground: 'hsl(var(--accent-foreground))',
                },
                popover: {
                    DEFAULT: 'hsl(var(--popover))',
                    foreground: 'hsl(var(--popover-foreground))',
                },
                card: {
                    DEFAULT: 'hsl(var(--card))',
                    foreground: 'hsl(var(--card-foreground))',
                },
            },
            borderRadius: {
                lg: 'var(--radius)',
                md: 'calc(var(--radius) - 2px)',
                sm: 'calc(var(--radius) - 4px)',
            },
            borderWidth: {
                '3': '3px',
            },
            boxShadow: {
                'neo': '5px 5px 0px 0px hsl(var(--foreground))',
                'neo-sm': '3px 3px 0px 0px hsl(var(--foreground))',
                'neo-lg': '8px 8px 0px 0px hsl(var(--foreground))',
                'neo-red': '5px 5px 0px 0px hsl(0 85% 57%)',
                'neo-hover': '7px 7px 0px 0px hsl(var(--foreground))',
                'neo-active': '2px 2px 0px 0px hsl(var(--foreground))',
            },
            keyframes: {
                'accordion-down': {
                    from: { height: '0' },
                    to: { height: 'var(--radix-accordion-content-height)' },
                },
                'accordion-up': {
                    from: { height: 'var(--radix-accordion-content-height)' },
                    to: { height: '0' },
                },
                'wiggle': {
                    '0%, 100%': { transform: 'rotate(0deg)' },
                    '25%': { transform: 'rotate(-2deg)' },
                    '75%': { transform: 'rotate(2deg)' },
                },
                'neo-pop': {
                    '0%': { transform: 'scale(0.95)', opacity: '0' },
                    '50%': { transform: 'scale(1.02)' },
                    '100%': { transform: 'scale(1)', opacity: '1' },
                },
                'neo-slide-in': {
                    '0%': { transform: 'translateY(10px)', opacity: '0' },
                    '100%': { transform: 'translateY(0)', opacity: '1' },
                },
            },
            animation: {
                'accordion-down': 'accordion-down 0.2s ease-out',
                'accordion-up': 'accordion-up 0.2s ease-out',
                'wiggle': 'wiggle 0.3s ease-in-out',
                'neo-pop': 'neo-pop 0.3s ease-out',
                'neo-slide-in': 'neo-slide-in 0.3s ease-out',
            },
        },
    },
    plugins: [require('tailwindcss-animate')],
}
