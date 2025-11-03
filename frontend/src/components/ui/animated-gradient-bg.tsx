"use client"
import { cn } from "@/lib/utils"
import { useEffect, useState } from "react"

interface AnimatedGradientBgProps {
  className?: string
  children?: React.ReactNode
}

export function AnimatedGradientBg({ className, children }: AnimatedGradientBgProps) {
  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 })

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      setMousePosition({ x: e.clientX, y: e.clientY })
    }

    window.addEventListener('mousemove', handleMouseMove)
    return () => window.removeEventListener('mousemove', handleMouseMove)
  }, [])

  return (
    <div 
      className={cn(
        "relative min-h-screen overflow-hidden bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900",
        className
      )}
    >
      {/* Animated gradient orbs */}
      <div className="absolute inset-0">
        <div 
          className="absolute w-96 h-96 rounded-full bg-blue-500/20 blur-3xl animate-pulse"
          style={{
            left: `${mousePosition.x * 0.05}px`,
            top: `${mousePosition.y * 0.05}px`,
            transform: 'translate(-50%, -50%)'
          }}
        />
        <div 
          className="absolute w-96 h-96 rounded-full bg-purple-500/20 blur-3xl animate-pulse"
          style={{
            right: `${-mousePosition.x * 0.03}px`,
            top: `${-mousePosition.y * 0.03}px`,
            transform: 'translate(50%, -50%)'
          }}
        />
        <div 
          className="absolute w-96 h-96 rounded-full bg-pink-500/20 blur-3xl animate-pulse"
          style={{
            left: '50%',
            bottom: `${-mousePosition.y * 0.02}px`,
            transform: 'translate(-50%, 50%)'
          }}
        />
      </div>

      {/* Grid pattern overlay */}
      <div className="absolute inset-0 opacity-20" style={{
        backgroundImage: `url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%239C92AC' fill-opacity='0.1'%3E%3Ccircle cx='30' cy='30' r='2'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")`
      }} />

      {/* Content */}
      <div className="relative z-10">
        {children}
      </div>
    </div>
  )
}
