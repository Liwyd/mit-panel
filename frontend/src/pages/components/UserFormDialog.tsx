import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { userSchema, UserFormData, ClientsOutput } from '@/types'
import { userAPI } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import { AlertCircle, Loader2, Shuffle } from 'lucide-react'

interface UserFormDialogProps {
    isOpen: boolean
    onClose: () => void
    onSuccess: () => void
    user?: ClientsOutput | null
    existingUsernames?: string[]
}

// Random username: 5 to 7 English digits, avoiding names already in use.
function generateRandomUsername(taken: Set<string>): string {
    for (let attempt = 0; attempt < 50; attempt++) {
        const length = 5 + Math.floor(Math.random() * 3) // 5, 6 or 7
        const bytes = crypto.getRandomValues(new Uint8Array(length))
        let name = ''
        for (const b of bytes) {
            name += String(b % 10)
        }
        if (!taken.has(name)) {
            return name
        }
    }
    // Fell through 50 collisions: widen to the longest allowed length.
    const bytes = crypto.getRandomValues(new Uint8Array(7))
    let name = ''
    for (const b of bytes) {
        name += String(b % 10)
    }
    return name
}

export function UserFormDialog({ isOpen, onClose, onSuccess, user, existingUsernames = [] }: UserFormDialogProps): JSX.Element {
    const [serverError, setServerError] = useState<string | null>(null)
    // Expiry as it stands on the server, kept so an edit that doesn't touch the
    // days field re-sends the exact same timestamp instead of a rounded date.
    const [originalExpiry, setOriginalExpiry] = useState<{ days: number; unix: number } | null>(null)

    const {
        register,
        handleSubmit,
        formState: { errors, isSubmitting },
        reset,
        setValue,
    } = useForm<UserFormData>({
        resolver: zodResolver(userSchema),
        defaultValues: {
            email: '',
            totalGb: 0.1,
            expiryDatetime: null,
        },
    })

    useEffect(() => {
        if (user) {
            setValue('email', user.username)
            setValue('totalGb', user.data_limit / (1024 ** 3))
            if (user.expiry_date_unix) {
                const exp = new Date(user.expiry_date_unix)
                const today = new Date()
                today.setHours(0, 0, 0, 0)
                const diffMs = exp.getTime() - today.getTime()
                const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24))
                const days = diffDays > 0 ? diffDays : 0
                setValue('expiryDatetime', days)
                setOriginalExpiry({ days, unix: user.expiry_date_unix })
            } else {
                setOriginalExpiry(null)
            }
        } else {
            reset()
            setOriginalExpiry(null)
        }
    }, [user, isOpen, setValue, reset])

    const handleRandomUsername = () => {
        const taken = new Set(existingUsernames)
        setValue('email', generateRandomUsername(taken), { shouldValidate: true })
    }

    const onSubmit = async (data: UserFormData) => {
        setServerError(null)

        try {
            // Convert expiry days (number) to date string YYYY-MM-DD for backend
            let expiryForSubmit: string | number | null | undefined = null
            if (data.expiryDatetime === null || data.expiryDatetime === undefined || data.expiryDatetime === '') {
                expiryForSubmit = null
            } else if (
                originalExpiry !== null &&
                typeof data.expiryDatetime === 'number' &&
                data.expiryDatetime === originalExpiry.days
            ) {
                // Days field untouched - resend the stored timestamp verbatim so
                // editing something else never shortens the subscription.
                expiryForSubmit = originalExpiry.unix
            } else if (typeof data.expiryDatetime === 'number') {
                const d = new Date()
                d.setHours(0, 0, 0, 0)
                d.setDate(d.getDate() + Math.max(0, Math.floor(data.expiryDatetime)))
                const year = d.getFullYear()
                const month = String(d.getMonth() + 1).padStart(2, '0')
                const day = String(d.getDate()).padStart(2, '0')
                expiryForSubmit = `${year}-${month}-${day}`
            } else {
                expiryForSubmit = String(data.expiryDatetime)
            }

            if (user?.uuid || user?.username || user?.id) {
                await userAPI.updateUser(
                    user.uuid || user.username || '0',
                    data.email,
                    data.totalGb,
                    expiryForSubmit,
                    user.sub_id || '',
                    user.status,
                    user.flow || '',
                    user.id?.toString()
                )
            } else {
                // Create
                await userAPI.createUser(
                    data.email,
                    data.totalGb,
                    expiryForSubmit
                )
            }

            onSuccess()
        } catch (error: any) {
            console.error('Form submission error:', error)
            setServerError(error?.message || 'Operation failed')
        }
    }

    return (
        <Dialog open={isOpen} onOpenChange={onClose}>
            <DialogContent>
                <DialogHeader>
                    <DialogTitle>{user ? 'Edit User' : 'Create New User'}</DialogTitle>
                    <DialogDescription>
                        {user ? 'Update user information' : 'Add a new user to the system'}
                    </DialogDescription>
                </DialogHeader>

                <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
                    {serverError && (
                        <div className="flex items-gap-2 rounded-md bg-destructive/10 p-3 text-sm text-destructive border border-destructive/20">
                            <AlertCircle className="h-4 w-4 mr-2 flex-shrink-0 mt-0.5" />
                            <p>{serverError}</p>
                        </div>
                    )}

                    {/* Email */}
                    <div className="space-y-2">
                        <Label htmlFor="email">Username/Email *</Label>
                        <div className="flex gap-2">
                            <Input
                                id="email"
                                type="text"
                                placeholder="username or email"
                                disabled={isSubmitting || !!user}
                                className="flex-1"
                                {...register('email')}
                            />
                            {!user && (
                                <Button
                                    type="button"
                                    variant="outline"
                                    onClick={handleRandomUsername}
                                    disabled={isSubmitting}
                                    title="Generate a random 5-7 digit username"
                                >
                                    <Shuffle className="h-4 w-4 mr-2" />
                                    Random
                                </Button>
                            )}
                        </div>
                        {errors.email && (
                            <p className="text-sm text-destructive">{errors.email.message}</p>
                        )}
                    </div>

                    {/* Traffic in GB */}
                    <div className="space-y-2">
                        <Label htmlFor="totalGb">Traffic (GB) *</Label>
                        <Input
                            id="totalGb"
                            type="number"
                            step="0.1"
                            min="0.1"
                            placeholder="1.0"
                            disabled={isSubmitting}
                            {...register('totalGb', { valueAsNumber: true })}
                        />
                        {errors.totalGb && (
                            <p className="text-sm text-destructive">{errors.totalGb.message}</p>
                        )}
                        <p className="text-xs text-muted-foreground">Minimum 0.1 GB</p>
                    </div>

                    {/* Expiry Date */}
                    <div className="space-y-2">
                        <Label htmlFor="expiryDatetime">Expiry (days)</Label>
                        <Input
                            id="expiryDatetime"
                            type="number"
                            min={0}
                            step={1}
                            placeholder="Enter number of days (e.g. 10)"
                            disabled={isSubmitting}
                            {...register('expiryDatetime', { valueAsNumber: true })}
                        />
                        {errors.expiryDatetime && (
                            <p className="text-sm text-destructive">{errors.expiryDatetime.message}</p>
                        )}
                        <p className="text-xs text-muted-foreground">Optional - Leave empty for no expiry</p>
                    </div>
                </form>

                <DialogFooter className="gap-2 sm:gap-0">
                    <Button variant="outline" onClick={onClose} disabled={isSubmitting}>
                        Cancel
                    </Button>
                    <Button onClick={handleSubmit(onSubmit)} disabled={isSubmitting}>
                        {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                        {isSubmitting ? 'Saving...' : user ? 'Update User' : 'Create User'}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}
