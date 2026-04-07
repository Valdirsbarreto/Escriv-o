"use client"

import * as React from "react"
import { cn } from "@/lib/utils"

interface ProgressProps extends React.HTMLAttributes<HTMLDivElement> {
  value?: number
}

const Progress = React.forwardRef<HTMLDivElement, ProgressProps>(
  ({ className, value = 0, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          "relative h-2 w-full overflow-hidden rounded-full bg-zinc-900 border border-zinc-800/50",
          className
        )}
        {...props}
      >
        <div
          className="h-full w-full flex-1 bg-blue-600 transition-all duration-500 ease-in-out shadow-[0_0_10px_rgba(37,99,235,0.4)]"
          style={{ transform: `translateX(-${100 - (value || 0)}%)` }}
        />
      </div>
    )
  }
)
Progress.displayName = "Progress"

export { Progress }
