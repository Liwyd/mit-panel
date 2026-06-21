import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { loginSchema, LoginFormData } from '@/types'
import { authAPI, settingsAPI, getLogoUrl } from '@/lib/api'
import { setToken, getDecodedToken, isTokenValid } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ThemeToggle } from '@/components/ThemeToggle'
import { AlertCircle, Loader2 } from 'lucide-react'
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
        // If already logged in, redirect to dashboard
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

            // Store token
            setToken(response.access_token)

            // Decode token to get role
            const decoded = getDecodedToken()

            // Redirect based on role
            if (decoded?.role) {
                navigate('/', { replace: true })
            } else {
                setServerError('Failed to determine user role')
            }
        } catch (error: any) {
            console.error('Login error:', error)
            setServerError(
                error?.response?.data?.message ||
                error?.message ||
                'Failed to login. Please check your credentials.'
            )
        }
    }

    return (
        <div className="min-h-screen bg-gradient-to-br from-primary/5 via-background to-primary/5 flex items-center justify-center p-4">
            {/* Theme Toggle */}
            <div className="absolute top-4 right-4">
                <ThemeToggle />
            </div>

            <Card className="w-full max-w-sm">
                <CardHeader className="space-y-1">
                    <div className="flex justify-center py-2">
                        <img
                            src={branding.has_logo ? getLogoUrl() : logo}
                            alt={branding.login_title}
                            className={
                                branding.has_logo
                                    ? 'w-44 h-auto'
                                    : 'w-44 h-auto [filter:brightness(0.55)_saturate(1.4)] dark:[filter:none]'
                            }
                        />
                    </div>
                    {branding.login_title && (
                        <CardTitle className="text-xl text-center">{branding.login_title}</CardTitle>
                    )}
                    <CardDescription className="text-center">
                        Login to your admin panel
                    </CardDescription>
                </CardHeader>

                <CardContent>
                    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
                        {/* Server Error */}
                        {serverError && (
                            <div className="flex items-gap-2 rounded-md bg-destructive/10 p-3 text-sm text-destructive border border-destructive/20">
                                <AlertCircle className="h-4 w-4 mr-2 mt-0.5 flex-shrink-0" />
                                <p>{serverError}</p>
                            </div>
                        )}

                        {/* Username */}
                        <div className="space-y-2">
                            <Label htmlFor="username">Username</Label>
                            <Input
                                id="username"
                                placeholder="Enter your username"
                                disabled={isSubmitting}
                                {...register('username')}
                            />
                            {errors.username && (
                                <p className="text-sm text-destructive">{errors.username.message}</p>
                            )}
                        </div>

                        {/* Password */}
                        <div className="space-y-2">
                            <Label htmlFor="password">Password</Label>
                            <Input
                                id="password"
                                type="password"
                                placeholder="Enter your password"
                                disabled={isSubmitting}
                                {...register('password')}
                            />
                            {errors.password && (
                                <p className="text-sm text-destructive">{errors.password.message}</p>
                            )}
                        </div>

                        {/* Submit Button */}
                        <Button
                            type="submit"
                            className="w-full"
                            disabled={isSubmitting}
                        >
                            {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            {isSubmitting ? 'Logging in...' : 'Login'}
                        </Button>
                    </form>

                </CardContent>
            </Card>
        </div>
    )
}
