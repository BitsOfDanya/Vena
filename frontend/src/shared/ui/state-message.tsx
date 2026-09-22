import * as React from "react"

import { cn } from "@/shared/lib/utils"

export function StateMessage({
  title,
  description,
  action,
  className,
}: {
  title: string
  description?: string
  action?: React.ReactNode
  className?: string
}) {
  return (
    <div role="status" className={cn("flex h-full min-h-32 flex-col items-start justify-center gap-1.5 px-6 py-8", className)}>
      <p className="text-[11px] font-medium tracking-[0.08em] text-faint uppercase">{title}</p>
      {description ? <p className="max-w-md text-sm text-muted-foreground">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  )
}

export function LoadingBar({ className }: { className?: string }) {
  return (
    <div role="status" aria-label="Загрузка" className={cn("h-full min-h-32 w-full animate-pulse bg-surface/60", className)} />
  )
}
