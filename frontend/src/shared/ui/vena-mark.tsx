import { cn } from "@/shared/lib/utils"

export function VenaMark({ className, tile = false }: { className?: string; tile?: boolean }) {
  const ink = tile ? "var(--primary-foreground)" : "currentColor"
  return (
    <svg aria-hidden viewBox="0 0 32 32" className={cn("size-[26px] shrink-0", className)}>
      {tile ? <rect width="32" height="32" rx="2" fill="var(--vena)" /> : null}
      <g fill="none" stroke={ink} strokeWidth="2.2" strokeLinecap="square" strokeLinejoin="miter">
        <path d="M6.5 7.5 16 25.5 25.5 7.5" />
        <path d="M11.5 7.5 16 16 20.5 7.5" />
      </g>
      <rect x="14.2" y="23.8" width="3.6" height="3.6" fill={tile ? "var(--brass)" : "currentColor"} />
    </svg>
  )
}

export function VenaLogo({ className, compact = false }: { className?: string; compact?: boolean }) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <VenaMark tile className="size-8" />
      {compact ? null : (
        <span className="flex flex-col leading-none">
          <span className="font-mono text-[16px] font-medium tracking-[0.28em] text-foreground">VENA</span>
          <span className="mt-1 text-[10.5px] tracking-[0.02em] text-muted-foreground">мониторинг коллекторов</span>
        </span>
      )}
    </span>
  )
}
