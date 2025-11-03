"use client"
import { cn } from "@/lib/utils"
import { forwardRef } from "react"
import { Button } from "./button"

interface GradientButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "outline" | "ghost"
  size?: "sm" | "md" | "lg" | "xl"
  gradient?: "blue" | "purple" | "pink" | "green" | "orange"
}

const GradientButton = forwardRef<HTMLButtonElement, GradientButtonProps>(
  ({ className, variant = "primary", size = "md", gradient = "blue", children, ...props }, ref) => {
    const gradients = {
      blue: "bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-700 hover:to-cyan-700",
      purple: "bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700",
      pink: "bg-gradient-to-r from-pink-600 to-rose-600 hover:from-pink-700 hover:to-rose-700",
      green: "bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-700 hover:to-emerald-700",
      orange: "bg-gradient-to-r from-orange-600 to-amber-600 hover:from-orange-700 hover:to-amber-700"
    }

    const sizes = {
      sm: "px-4 py-2 text-sm",
      md: "px-6 py-3 text-base",
      lg: "px-8 py-4 text-lg",
      xl: "px-10 py-5 text-xl"
    }

    const variants = {
      primary: `${gradients[gradient]} text-white shadow-lg hover:shadow-xl transform hover:scale-105 transition-all duration-200`,
      secondary: "bg-white/10 backdrop-blur-md border border-white/20 text-white hover:bg-white/20 transition-all duration-200",
      outline: "border-2 border-white/30 text-white hover:bg-white/10 hover:border-white/50 transition-all duration-200",
      ghost: "text-white/80 hover:text-white hover:bg-white/10 transition-all duration-200"
    }

    return (
      <Button
        ref={ref}
        className={cn(
          "rounded-xl font-semibold",
          sizes[size],
          variants[variant],
          className
        )}
        {...props}
      >
        <span className="relative z-10">{children}</span>
      </Button>
    )
  }
)
GradientButton.displayName = "GradientButton"

export { GradientButton }
