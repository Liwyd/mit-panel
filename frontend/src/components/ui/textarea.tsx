import * as React from "react"
import { cn } from "@/lib/utils"

export interface TextareaProps
    extends React.TextareaHTMLAttributes<HTMLTextAreaElement> { }

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
    ({ className, ...props }, ref) => (
        <textarea
            className={cn(
                "flex min-h-[80px] w-full rounded-lg border-3 border-foreground bg-background px-4 py-2 text-sm font-medium shadow-neo-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-primary focus-visible:shadow-[4px_4px_0px_0px_hsl(var(--primary))] disabled:cursor-not-allowed disabled:opacity-50 transition-all duration-100",
                className
            )}
            ref={ref}
            {...props}
        />
    )
)
Textarea.displayName = "Textarea"

export { Textarea }
