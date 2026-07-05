import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { loginSchema, LoginFormData } from '@/types'
import { authAPI, settingsAPI, getLogoUrl } from '@/lib/api'
import { setToken, getDecodedToken, isTokenValid } from '@/lib/auth'
import logo from '@/assets/logo.png'

export function LoginPage() {
    const navigate = useNavigate()
    const [serverError, setServerError] = useState<string | null>(null)
    const [branding, setBranding] = useState<{ login_title: string; has_logo: boolean }>({
        login_title: 'MIT Panel',
        has_logo: false,
    })

    useEffect(() => {
        settingsAPI.getBranding().then(setBranding).catch(() => { })
    }, [])

    useEffect(() => {
        if (isTokenValid()) {
            navigate('/', { replace: true })
        }
    }, [navigate])

    const {
        register,
        handleSubmit,
        formState: { errors, isSubmitting },
    } = useForm<LoginFormData>({
        resolver: zodResolver(loginSchema),
    })

    const onSubmit = async (data: LoginFormData) => {
        setServerError(null)
        try {
            const response = await authAPI.login(data.username, data.password)
            setToken(response.access_token)
            const decoded = getDecodedToken()
            if (decoded?.role) {
                navigate('/', { replace: true })
            } else {
                setServerError('نقش کاربر مشخص نشد')
            }
        } catch (error: any) {
            console.error('Login error:', error)
            setServerError(error?.message || 'ورود ناموفق بود. اطلاعات ورود را بررسی کنید.')
        }
    }

    return (
        <div className="fixed inset-0 z-0 bg-background flex items-center justify-center p-6">
            <div className="absolute inset-0 bg-[radial-gradient(hsl(var(--border))_1px,transparent_1px)] [background-size:22px_22px] opacity-50" />

            <main className="w-full max-w-md relative animate-neo-pop">
                <div className="neo-card p-8">
                    <div className="flex items-center gap-3 mb-6">
                        <div className="w-2.5 h-2.5 rounded-full bg-primary animate-pulse" />
                        <span className="text-xs font-medium text-muted-foreground">
                            Panel Access
                        </span>
                    </div>

                    <div className="flex justify-center mb-6">
                        <img
                            src={branding.has_logo ? getLogoUrl() : logo}
                            alt={branding.login_title}
                            className="w-32 h-auto"
                        />
                    </div>

                    <h1 className="text-2xl font-semibold mb-2">
                        Sign In
                    </h1>
                    <p className="text-sm text-muted-foreground mb-6">
                        Enter your credentials to access {branding.login_title}.
                    </p>

                    {serverError && (
                        <div className="rounded-lg bg-destructive/10 border-2 border-destructive p-3 text-sm text-destructive mb-4" dir="auto">
                            {serverError}
                        </div>
                    )}

                    <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
                        <div className="space-y-2">
                            <label className="text-sm font-medium text-foreground">
                                Username
                            </label>
                            <input
                                type="text"
                                placeholder="username"
                                autoCapitalize="off"
                                spellCheck={false}
                                disabled={isSubmitting}
                                className="neo-input w-full h-11 px-4 text-sm"
                                {...register('username')}
                            />
                            {errors.username && (
                                <p className="text-xs text-destructive">{errors.username.message}</p>
                            )}
                        </div>

                        <div className="space-y-2">
                            <label className="text-sm font-medium text-foreground">
                                Password
                            </label>
                            <input
                                type="password"
                                placeholder="password"
                                disabled={isSubmitting}
                                className="neo-input w-full h-11 px-4 text-sm"
                                {...register('password')}
                            />
                            {errors.password && (
                                <p className="text-xs text-destructive">{errors.password.message}</p>
                            )}
                        </div>

                        <button
                            type="submit"
                            disabled={isSubmitting}
                            className="neo-btn w-full h-11 bg-primary text-primary-foreground text-sm"
                        >
                            {isSubmitting ? 'Signing in...' : 'Sign In'}
                        </button>
                    </form>

                    <div className="mt-6 pt-4 border-t border-border flex justify-between text-xs text-muted-foreground">
                        <span>Status: Ready</span>
                        <span>MIT</span>
                    </div>
                </div>
            </main>
        </div>
    )
}
