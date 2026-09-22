import { X } from "lucide-react"
import * as React from "react"

import { cn } from "@/shared/lib/utils"

export function Inspector({ className, children, label }: { className?: string; children: React.ReactNode; label: string }) {
  return (
    <aside
      aria-label={label}
      className={cn(
        "vena-reveal absolute inset-y-0 right-0 z-20 flex h-full w-[380px] max-w-full shrink-0 flex-col overflow-hidden border-l bg-surface lg:static",
        className
      )}
    >
      {children}
    </aside>
  )
}

export function InspectorHeader({
  eyebrow,
  title,
  onClose,
  children,
}: {
  eyebrow?: string
  title: string
  onClose?: () => void
  children?: React.ReactNode
}) {
  return (
    <div className="flex items-start gap-3 border-b px-4 py-3">
      <div className="min-w-0 flex-1">
        {eyebrow ? <p className="text-[11px] font-medium tracking-[0.08em] text-faint uppercase">{eyebrow}</p> : null}
        <h2 className="truncate font-mono text-[15px] font-medium text-foreground tabular-nums">{title}</h2>
        {children}
      </div>
      {onClose ? (
        <button
          type="button"
          onClick={onClose}
          aria-label="Close inspector"
          className="mt-0.5 flex size-6 items-center justify-center rounded-sm text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/60"
        >
          <X className="size-4" aria-hidden />
        </button>
      ) : null}
    </div>
  )
}

export function InspectorSection({
  title,
  children,
  className,
}: {
  title?: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <section className={cn("border-b px-4 py-3 last:border-b-0", className)}>
      {title ? <h3 className="mb-2 text-[11px] font-medium tracking-[0.1em] text-muted-foreground uppercase">{title}</h3> : null}
      {children}
    </section>
  )
}

export function InspectorBody({ children }: { children: React.ReactNode }) {
  return <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
}

export function InspectorFooter({ children }: { children: React.ReactNode }) {
  return <div className="flex shrink-0 gap-2 border-t bg-surface px-4 py-3">{children}</div>
}
