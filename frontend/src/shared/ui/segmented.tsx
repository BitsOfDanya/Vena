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
    <div role="radiogroup" aria-label={label} className={cn("inline-flex h-8 items-stretch gap-0.5 rounded-md bg-surface p-0.5", className)}>
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
              "relative cursor-pointer rounded-[5px] px-2.5 text-[13px] whitespace-nowrap outline-none transition-colors focus-visible:z-10 focus-visible:ring-2 focus-visible:ring-ring/60",
              active ? "bg-elevated font-medium text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
              option.disabled && "cursor-not-allowed opacity-40 hover:text-muted-foreground"
            )}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}
