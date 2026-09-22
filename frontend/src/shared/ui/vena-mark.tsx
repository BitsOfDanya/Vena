import { cn } from "@/shared/lib/utils"

export function VenaMark({ className }: { className?: string }) {
  return (
    <svg aria-hidden viewBox="0 0 24 24" className={cn("size-[22px]", className)}>
      <g fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
        <path d="M3.5 3.5 10.6 11.2" />
        <path d="M20.5 3.5 13.4 11.2" />
        <path d="M12 15.4V20.5" />
      </g>
      <path d="M12 9.6 14.4 12.3 12 15 9.6 12.3Z" fill="currentColor" />
    </svg>
  )
}
