import { cn } from "@/shared/lib/utils"

export function VenaMark({ className, tile = false }: { className?: string; tile?: boolean }) {
  return (
    <svg aria-hidden viewBox="0 0 32 32" className={cn("size-[26px] shrink-0", className)}>
      {tile ? <rect width="32" height="32" rx="2" fill="var(--vena)" /> : null}
      <g
        fill="none"
        stroke={tile ? "var(--primary-foreground)" : "currentColor"}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M7.5 24V15.5a8.5 8.5 0 0 1 17 0V24" strokeWidth="2.2" />
        <path d="M5 24h22" strokeWidth="2.2" />
        <path d="M9.5 18.5h3l1.6-3.6 2.4 6 1.8-4.2 1.1 1.8h3.1" strokeWidth="1.9" />
      </g>
    </svg>
  )
}

export function VenaLogo({ className, compact = false }: { className?: string; compact?: boolean }) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <VenaMark tile className="size-8" />
      {compact ? null : (
        <span className="flex flex-col leading-none">
          <span className="text-[16px] font-semibold tracking-[0.14em] text-foreground">VENA</span>
          <span className="mt-1 text-[10.5px] font-medium tracking-[0.02em] text-muted-foreground">
            мониторинг коллекторов
          </span>
        </span>
      )}
    </span>
  )
}
