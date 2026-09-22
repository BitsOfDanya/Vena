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
    <div role="radiogroup" aria-label={label} className={cn("inline-flex h-7 items-stretch rounded-md border bg-surface", className)}>
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
              "relative px-2.5 text-[11px] font-medium tracking-[0.08em] uppercase outline-none first:rounded-l-[5px] last:rounded-r-[5px] focus-visible:z-10 focus-visible:ring-2 focus-visible:ring-ring/60",
              active ? "bg-elevated text-foreground" : "text-muted-foreground hover:text-foreground",
              option.disabled && "cursor-not-allowed opacity-40 hover:text-muted-foreground"
            )}
          >
            {option.label}
            {active ? <span aria-hidden className="absolute inset-x-1.5 bottom-0 h-px bg-vena" /> : null}
          </button>
        )
      })}
    </div>
  )
}
