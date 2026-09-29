"use client"

import { cn } from "@/shared/lib/utils"

type Option<T extends string | number> = {
  value: T
  label: string
  disabled?: boolean
  title?: string
}

type SegmentedProps<T extends string | number> = {
  value: T
  options: Option<T>[]
  onChange: (value: T) => void
  label: string
  className?: string
}

export function Segmented<T extends string | number>({ value, options, onChange, label, className }: SegmentedProps<T>) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={cn("inline-flex h-8 items-stretch divide-x divide-border border border-border bg-elevated", className)}
    >
      {options.map((option) => {
        const active = option.value === value
        return (
          <button
            key={String(option.value)}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={option.disabled}
            title={option.title}
            onClick={() => onChange(option.value)}
            className={cn(
              "relative cursor-pointer px-3 text-[13px] whitespace-nowrap outline-none transition-colors focus-visible:z-10 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/60",
              active ? "bg-accent font-medium text-foreground" : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
              option.disabled && "cursor-not-allowed opacity-40 hover:bg-transparent hover:text-muted-foreground"
            )}
          >
            {option.label}
            {active ? <span aria-hidden className="absolute inset-x-0 -bottom-px h-[2px] bg-vena" /> : null}
          </button>
        )
      })}
    </div>
  )
}
