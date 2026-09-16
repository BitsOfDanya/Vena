"use client"

import { useQuery } from "@tanstack/react-query"
import { CheckCircle2, RefreshCw, Server } from "lucide-react"

import { getHealth } from "@/entities/system"
import { Badge } from "@/shared/ui/badge"
import { Button } from "@/shared/ui/button"
import { Spinner } from "@/shared/ui/spinner"

export function HealthStatus() {
  const healthQuery = useQuery({
    queryKey: ["system", "health"],
    queryFn: getHealth,
    retry: 1,
  })

  if (healthQuery.isPending) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Spinner /> Проверяем API
      </div>
    )
  }

  if (healthQuery.isError) {
    return (
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="size-2 rounded-full bg-amber-400" />
          <span className="text-sm text-muted-foreground">API ожидает запуска</span>
        </div>
        <Button
          aria-label="Повторить проверку API"
          onClick={() => healthQuery.refetch()}
          size="icon-sm"
          variant="ghost"
        >
          <RefreshCw />
        </Button>
      </div>
    )
  }

  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <span className="grid size-7 place-items-center rounded-full bg-emerald-100 text-emerald-700">
          <CheckCircle2 className="size-4" />
        </span>
        <div>
          <p className="text-sm font-medium">API подключён</p>
          <p className="text-xs text-muted-foreground">{healthQuery.data.service}</p>
        </div>
      </div>
      <Badge variant="secondary">
        <Server data-icon="inline-start" />v{healthQuery.data.version}
      </Badge>
    </div>
  )
}
