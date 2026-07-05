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
  --bg:#0a0a0a; --panel:#111111; --line:#242424; --ink:#f2f2f2; --mut:#6f6f6f; --accent:#2ee6ff;
  --mono:"SFMono-Regular",Menlo,Consolas,"Liberation Mono",monospace;
  background:var(--bg); color:var(--ink);
  display:flex; align-items:center; justify-content:center; padding:24px;
  -webkit-font-smoothing:antialiased;
  background-image:radial-gradient(var(--line) 1px,transparent 1px);
  background-size:22px 22px;
}
.nx-card{
  width:100%; max-width:392px;
  background:var(--panel); border:1px solid var(--line);
  border-radius:20px; padding:38px 32px 26px;
  position:relative; overflow:hidden;
}
.nx-card::before,.nx-card::after{content:"";position:absolute;width:9px;height:9px;border:1px solid var(--accent);opacity:.55}
.nx-card::before{top:14px;left:14px;border-right:0;border-bottom:0}
.nx-card::after{bottom:14px;right:14px;border-left:0;border-top:0}
.nx-brand{display:flex;align-items:center;gap:9px;font-family:var(--mono);font-size:11px;letter-spacing:.28em;text-transform:uppercase;color:var(--mut);margin-bottom:24px}
.nx-dot{width:8px;height:8px;border-radius:50%;background:var(--accent);box-shadow:0 0 12px 1px rgba(46,230,255,.55)}
.nx-logo{display:flex;justify-content:center;margin-bottom:18px}
.nx-logo img{width:132px;height:auto;filter:drop-shadow(0 0 18px rgba(46,230,255,.22))}
.nx-title{font-family:var(--mono);font-weight:500;font-size:21px;letter-spacing:.02em;line-height:1.1;margin-bottom:10px}
.nx-title .cur{color:var(--accent);animation:nxblink 1.2s steps(1) infinite}
@keyframes nxblink{50%{opacity:0}}
.nx-sub{font-size:13px;color:var(--mut);line-height:1.55;margin-bottom:26px}
.nx-err{border:1px solid var(--accent);color:var(--accent);background:rgba(46,230,255,.07);border-radius:10px;padding:11px 13px;font-family:var(--mono);font-size:12.5px;margin-bottom:16px;line-height:1.55}
.nx-form{display:flex;flex-direction:column;gap:16px}
.nx-field{position:relative}
.nx-field label{position:absolute;top:-7px;left:12px;background:var(--panel);padding:0 6px;font-family:var(--mono);font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--mut)}
.nx-field input{width:100%;background:transparent;border:1px solid var(--line);border-radius:11px;padding:15px 14px;color:var(--ink);font-family:var(--mono);font-size:14px;letter-spacing:.02em;transition:border-color .15s ease}
.nx-field input:focus{outline:none;border-color:var(--accent)}
.nx-field input::placeholder{color:#3a3a3a}
.nx-fielderr{color:var(--accent);font-family:var(--mono);font-size:11px;margin-top:6px}
.nx-btn{margin-top:6px;width:100%;background:var(--ink);color:#000;border:0;border-radius:11px;padding:16px;font-family:var(--mono);font-size:12px;letter-spacing:.2em;text-transform:uppercase;cursor:pointer;transition:transform .08s ease,background .15s ease}
.nx-btn:hover{background:#fff}
.nx-btn:active{transform:translateY(1px)}
.nx-btn:disabled{opacity:.55;cursor:default}
.nx-foot{margin-top:24px;padding-top:16px;border-top:1px solid var(--line);display:flex;justify-content:space-between;font-family:var(--mono);font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--mut)}
@media (prefers-reduced-motion:reduce){.nx-title .cur,.nx-dot{animation:none}}
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

                <h1 className="nx-title">Sign in<span className="cur">_</span></h1>
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
