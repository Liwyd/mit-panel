import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
    "inline-flex items-center justify-center whitespace-nowrap rounded-lg text-sm font-bold uppercase tracking-wider border-3 border-foreground transition-all duration-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 active:translate-x-[2px] active:translate-y-[2px] active:shadow-none",
    {
        variants: {
            variant: {
                default: "bg-primary text-primary-foreground shadow-neo hover:shadow-neo-hover hover:-translate-x-0.5 hover:-translate-y-0.5",
                destructive:
                    "bg-destructive text-destructive-foreground shadow-neo hover:shadow-neo-hover hover:-translate-x-0.5 hover:-translate-y-0.5",
                outline:
                    "bg-background text-foreground shadow-neo hover:shadow-neo-hover hover:-translate-x-0.5 hover:-translate-y-0.5 hover:bg-accent hover:text-accent-foreground",
                secondary:
                    "bg-secondary text-secondary-foreground shadow-neo hover:shadow-neo-hover hover:-translate-x-0.5 hover:-translate-y-0.5",
                ghost: "border-transparent shadow-none hover:bg-accent hover:text-accent-foreground hover:shadow-neo-sm hover:border-foreground",
                link: "text-primary underline-offset-4 hover:underline border-transparent shadow-none",
            },
            size: {
                default: "h-11 px-5 py-2",
                sm: "h-9 rounded-lg px-3 text-xs",
                xs: "h-7 rounded-md px-2 text-xs",
                lg: "h-12 rounded-lg px-8 text-base",
                icon: "h-11 w-11",
            },
        },
        defaultVariants: {
            variant: "default",
            size: "default",
        },
    }
)

export interface ButtonProps
    extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> { }

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
    ({ className, variant, size, ...props }, ref) => {
        return (
            <button
                className={cn(buttonVariants({ variant, size, className }))}
                ref={ref}
                {...props}
            />
        )
    }
)
Button.displayName = "Button"

export { Button, buttonVariants }
