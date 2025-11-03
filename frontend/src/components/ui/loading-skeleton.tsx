"use client"
import { cn } from "@/lib/utils"

interface LoadingSkeletonProps {
  className?: string
  variant?: "text" | "circular" | "rectangular" | "rounded"
  width?: string | number
  height?: string | number
  lines?: number
}

export function LoadingSkeleton({ 
  className, 
  variant = "text", 
  width, 
  height, 
  lines = 3 
}: LoadingSkeletonProps) {
  const variants = {
    text: "h-4 rounded",
    circular: "rounded-full",
    rectangular: "",
    rounded: "rounded-lg"
  }

  if (variant === "text" && lines > 1) {
    return (
      <div className={cn("space-y-2", className)}>
        {Array.from({ length: lines }).map((_, i) => (
          <div
            key={i}
            className={cn(
              "h-4 bg-white/10 rounded animate-pulse",
              i === lines - 1 ? "w-3/4" : "w-full"
            )}
            style={{
              width: i === lines - 1 ? "75%" : "100%",
              height: height || "1rem"
            }}
          />
        ))}
      </div>
    )
  }

  return (
    <div
      className={cn(
        "bg-white/10 animate-pulse",
        variants[variant],
        className
      )}
      style={{
        width: width || "100%",
        height: height || "1.5rem"
      }}
    />
  )
}
