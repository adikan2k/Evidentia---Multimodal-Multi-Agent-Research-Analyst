"use client"
import { cn } from "@/lib/utils"
import { forwardRef } from "react"

interface GlassCardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "subtle" | "strong"
}

const GlassCard = forwardRef<HTMLDivElement, GlassCardProps>(
  ({ className, variant = "default", ...props }, ref) => {
    const variants = {
      default: "bg-white/10 backdrop-blur-md border border-white/20 shadow-xl",
      subtle: "bg-white/5 backdrop-blur-sm border border-white/10 shadow-lg",
      strong: "bg-white/20 backdrop-blur-lg border border-white/30 shadow-2xl"
    }

    return (
      <div
        ref={ref}
        className={cn(
          "relative rounded-2xl transition-all duration-300 hover:shadow-2xl",
          variants[variant],
          className
        )}
        {...props}
      />
    )
  }
)
GlassCard.displayName = "GlassCard"

export { GlassCard }
