import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { loginSchema, LoginFormData } from '@/types'
import { authAPI, settingsAPI, getLogoUrl } from '@/lib/api'
import { setToken, getDecodedToken, isTokenValid } from '@/lib/auth'
import logo from '@/assets/logo.png'

const styles = `
.nx-login-root{
  position:fixed; inset:0; z-index:0;
  background:hsl(var(--background)); color:hsl(var(--foreground));
  display:flex; align-items:center; justify-content:center; padding:24px;
  -webkit-font-smoothing:antialiased;
  background-image:radial-gradient(ellipse 70% 50% at 50% -10%, hsl(var(--brand-blue) / .12), transparent 62%);
}
.nx-card{
  width:100%; max-width:412px;
  background:var(--surface-gradient);
  border:1px solid hsl(var(--border));
  border-radius:1.75rem; padding:36px 32px 24px;
  box-shadow:inset 0 1px 0 0 var(--surface-highlight), var(--surface-shadow);
  position:relative; overflow:hidden;
}
.nx-brand{display:flex;align-items:center;gap:9px;font-size:11px;font-weight:800;letter-spacing:.22em;text-transform:uppercase;color:hsl(var(--muted-foreground));margin-bottom:22px}
.nx-dot{width:8px;height:8px;border-radius:50%;background:hsl(var(--brand-blue));box-shadow:0 0 12px 1px hsl(var(--brand-blue) / .5)}
.nx-logo{display:flex;justify-content:center;margin-bottom:18px}
.nx-logo img{width:132px;height:auto}
.nx-title{font-weight:900;font-size:28px;letter-spacing:-.02em;line-height:1.3;margin-bottom:8px;color:hsl(var(--foreground))}
.nx-sub{font-size:14px;color:hsl(var(--muted-foreground));line-height:1.8;margin-bottom:24px}
.nx-err{border:1px solid hsl(var(--destructive) / .35);color:hsl(var(--destructive));background:hsl(var(--destructive) / .08);border-radius:12px;padding:11px 13px;font-size:13px;margin-bottom:16px;line-height:1.6}
.nx-form{display:flex;flex-direction:column;gap:18px}
.nx-field{position:relative}
.nx-field label{position:absolute;top:-7px;left:12px;background:hsl(var(--card));padding:0 6px;font-size:10px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:hsl(var(--muted-foreground))}
.nx-field input{width:100%;background:hsl(var(--card));border:1px solid hsl(var(--input));border-radius:12px;padding:15px 14px;color:hsl(var(--foreground));font-family:inherit;font-size:14px;transition:border-color .15s ease,box-shadow .15s ease}
.nx-field input:focus{outline:none;border-color:hsl(var(--brand-blue));box-shadow:0 0 0 3px hsl(var(--brand-blue) / .18)}
.nx-field input::placeholder{color:hsl(var(--muted-foreground) / .6)}
.nx-fielderr{color:hsl(var(--destructive));font-size:12px;margin-top:6px}
.nx-btn{margin-top:6px;width:100%;background:hsl(var(--primary));color:hsl(var(--primary-foreground));border:0;border-radius:12px;padding:16px;font-family:inherit;font-size:14px;font-weight:800;cursor:pointer;box-shadow:0 12px 28px rgba(19,34,56,.16);transition:transform .18s ease,background .15s ease,box-shadow .18s ease}
.nx-btn:hover{background:hsl(var(--primary) / .9);transform:translateY(-2px)}
.nx-btn:active{transform:translateY(0)}
.nx-btn:disabled{opacity:.55;cursor:default;transform:none}
.nx-foot{margin-top:24px;padding-top:16px;border-top:1px solid hsl(var(--border));display:flex;justify-content:space-between;font-size:10px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:hsl(var(--muted-foreground))}
@media (prefers-reduced-motion:reduce){.nx-dot{animation:none}}
`

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
        <div className="nx-login-root">
            <style>{styles}</style>
            <main className="nx-card">
                <div className="nx-brand"><span className="nx-dot" /> Panel Access</div>

                <div className="nx-logo">
                    <img src={branding.has_logo ? getLogoUrl() : logo} alt={branding.login_title} />
                </div>

                <h1 className="nx-title">Sign in</h1>
                <p className="nx-sub">Enter your credentials to access {branding.login_title}.</p>

                {serverError && (
                    <div className="nx-err" dir="auto">{serverError}</div>
                )}

                <form className="nx-form" onSubmit={handleSubmit(onSubmit)}>
                    <div className="nx-field">
                        <label>User</label>
                        <input
                            type="text"
                            placeholder="username"
                            autoCapitalize="off"
                            spellCheck={false}
                            disabled={isSubmitting}
                            {...register('username')}
                        />
                        {errors.username && (
                            <div className="nx-fielderr">{errors.username.message}</div>
                        )}
                    </div>

                    <div className="nx-field">
                        <label>Pass</label>
                        <input
                            type="password"
                            placeholder="password"
                            disabled={isSubmitting}
                            {...register('password')}
                        />
                        {errors.password && (
                            <div className="nx-fielderr">{errors.password.message}</div>
                        )}
                    </div>

                    <button className="nx-btn" type="submit" disabled={isSubmitting}>
                        {isSubmitting ? 'Signing in…' : 'Sign in'}
                    </button>
                </form>

                <div className="nx-foot">
                    <span>Status · Ready</span>
                    <span>MIT</span>
                </div>
            </main>
        </div>
    )
}
