"use client"
import { cn } from "@/lib/utils"
import { forwardRef } from "react"

interface ProgressRingProps extends React.SVGAttributes<SVGSVGElement> {
  progress: number
  size?: number
  strokeWidth?: number
  className?: string
  color?: string
}

const ProgressRing = forwardRef<SVGSVGElement, ProgressRingProps>(
  ({ progress, size = 120, strokeWidth = 8, className, color = "url(#gradient)", ...props }, ref) => {
    const radius = (size - strokeWidth) / 2
    const circumference = radius * 2 * Math.PI
    const offset = circumference - (progress / 100) * circumference

    return (
      <svg
        ref={ref}
        width={size}
        height={size}
        className={cn("transform -rotate-90", className)}
        {...props}
      >
        <defs>
          <linearGradient id="gradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#3B82F6" />
            <stop offset="100%" stopColor="#06B6D4" />
          </linearGradient>
        </defs>
        
        {/* Background circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="rgba(255, 255, 255, 0.1)"
          strokeWidth={strokeWidth}
          fill="none"
        />
        
        {/* Progress circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={color}
          strokeWidth={strokeWidth}
          fill="none"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className="transition-all duration-500 ease-out"
        />
        
        {/* Center text */}
        <text
          x={size / 2}
          y={size / 2}
          textAnchor="middle"
          dominantBaseline="middle"
          className="fill-white text-lg font-semibold"
          transform="rotate(90 60 60)"
        >
          {progress}%
        </text>
      </svg>
    )
  }
)
ProgressRing.displayName = "ProgressRing"

export { ProgressRing }
