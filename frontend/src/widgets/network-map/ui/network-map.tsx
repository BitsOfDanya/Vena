"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"

import {
  extractMapGeometry,
  getSpatialCollection,
  type MapAssetPoint,
} from "@/entities/infrastructure/api/spatial-client"
import type { AssetStatus, NetworkNode } from "@/entities/infrastructure"
import { cn } from "@/shared/lib/utils"

const STATUS_FILL: Record<AssetStatus, string> = {
  normal: "var(--status-normal)",
  attention: "var(--status-attention)",
  critical: "var(--status-critical)",
  offline: "var(--status-offline, #8a8580)",
}

function project(
  lon: number,
  lat: number,
  bounds: { minLon: number; maxLon: number; minLat: number; maxLat: number },
  width: number,
  height: number,
  pad: number
) {
  const x = pad + ((lon - bounds.minLon) / Math.max(bounds.maxLon - bounds.minLon, 1e-9)) * (width - pad * 2)
  const y = pad + ((bounds.maxLat - lat) / Math.max(bounds.maxLat - bounds.minLat, 1e-9)) * (height - pad * 2)
  return { x, y }
}

function boundsOf(points: { lon: number; lat: number }[]) {
  const lons = points.map((point) => point.lon)
  const lats = points.map((point) => point.lat)
  const minLon = Math.min(...lons)
  const maxLon = Math.max(...lons)
  const minLat = Math.min(...lats)
  const maxLat = Math.max(...lats)
  const lonPad = Math.max((maxLon - minLon) * 0.12, 0.001)
  const latPad = Math.max((maxLat - minLat) * 0.12, 0.001)
  return {
    minLon: minLon - lonPad,
    maxLon: maxLon + lonPad,
    minLat: minLat - latPad,
    maxLat: maxLat + latPad,
  }
}

export function NetworkMap({
  nodes,
  selectedId,
  dimmed,
  onSelect,
}: {
  nodes: NetworkNode[]
  selectedId: string | null
  dimmed: Set<string>
  onSelect: (id: string) => void
}) {
  const spatial = useQuery({
    queryKey: ["infrastructure", "spatial"],
    queryFn: getSpatialCollection,
    staleTime: 60_000,
  })
  const statusById = React.useMemo(() => new Map(nodes.map((node) => [node.id, node.status])), [nodes])
  const geometry = React.useMemo(
    () =>
      spatial.data
        ? extractMapGeometry(spatial.data)
        : { assets: [] as MapAssetPoint[], corridor: null, collectors: [] as MapAssetPoint[] },
    [spatial.data]
  )

  const [view, setView] = React.useState({ scale: 1, tx: 0, ty: 0 })
  const drag = React.useRef<{ x: number; y: number; tx: number; ty: number } | null>(null)
  const width = 960
  const height = 640
  const pad = 36

  const points = geometry.assets.length > 0 ? geometry.assets : geometry.collectors
  const bounds =
    points.length > 0
      ? boundsOf([
          ...points,
          ...(geometry.corridor?.coordinates.map(([lon, lat]) => ({ lon, lat })) ?? []),
        ])
      : null

  if (spatial.isPending) {
    return <div className="flex size-full items-center justify-center text-sm text-muted-foreground">Загрузка карты…</div>
  }

  if (!bounds || points.length === 0) {
    return (
      <div className="flex size-full items-center justify-center px-8 text-center text-sm text-muted-foreground">
        Нет пространственных данных. Импортируйте GeoJSON/WKT через API `/spatial`.
      </div>
    )
  }

  const corridorPath =
    geometry.corridor?.coordinates
      .map((pair, index) => {
        const { x, y } = project(pair[0], pair[1], bounds, width, height, pad)
        return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`
      })
      .join(" ") ?? ""

  return (
    <div className="relative size-full min-h-0 overflow-hidden bg-[linear-gradient(180deg,color-mix(in_oklab,var(--elevated)_88%,#d7e0ea),color-mix(in_oklab,var(--surface)_92%,#c9d4c4))]">
      <p className="pointer-events-none absolute top-3 left-4 z-10 font-mono text-[11px] tracking-[0.08em] text-faint uppercase">
        Map · {spatial.data?.source === "demo_spatial" ? "demo spatial" : "GeoJSON"} · risk overlay
      </p>
      <svg
        role="img"
        aria-label="Infrastructure map"
        viewBox={`0 0 ${width} ${height}`}
        className="size-full cursor-grab active:cursor-grabbing"
        onWheel={(event) => {
          event.preventDefault()
          const next = Math.min(3.5, Math.max(0.7, view.scale * (event.deltaY < 0 ? 1.08 : 0.92)))
          setView((current) => ({ ...current, scale: next }))
        }}
        onPointerDown={(event) => {
          drag.current = { x: event.clientX, y: event.clientY, tx: view.tx, ty: view.ty }
          ;(event.currentTarget as Element).setPointerCapture?.(event.pointerId)
        }}
        onPointerMove={(event) => {
          if (!drag.current) return
          setView({
            scale: view.scale,
            tx: drag.current.tx + (event.clientX - drag.current.x),
            ty: drag.current.ty + (event.clientY - drag.current.y),
          })
        }}
        onPointerUp={() => {
          drag.current = null
        }}
      >
        <g transform={`translate(${view.tx} ${view.ty}) scale(${view.scale})`}>
          <rect x={0} y={0} width={width} height={height} fill="transparent" />
          {corridorPath ? (
            <path
              d={corridorPath}
              fill="none"
              stroke="color-mix(in oklab, var(--foreground) 28%, transparent)"
              strokeWidth={3.5}
              strokeLinecap="round"
            />
          ) : null}
          {geometry.collectors.map((collector) => {
            const { x, y } = project(collector.lon, collector.lat, bounds, width, height, pad)
            return (
              <g key={`c-${collector.assetId}`}>
                <circle
                  cx={x}
                  cy={y}
                  r={7}
                  fill="color-mix(in oklab, var(--foreground) 18%, transparent)"
                  stroke="var(--border)"
                  strokeWidth={1}
                />
                <text x={x + 10} y={y + 3} className="fill-muted-foreground text-[10px]">
                  {collector.groupId ?? collector.name}
                </text>
              </g>
            )
          })}
          {geometry.assets.map((asset) => {
            const status = statusById.get(asset.assetId) ?? "normal"
            const { x, y } = project(asset.lon, asset.lat, bounds, width, height, pad)
            const selected = selectedId === asset.assetId
            const isDimmed = dimmed.has(asset.assetId)
            return (
              <g
                key={asset.assetId}
                role="button"
                tabIndex={0}
                transform={`translate(${x} ${y})`}
                className={cn("cursor-pointer outline-none", isDimmed && "opacity-25")}
                aria-label={`Asset ${asset.assetId}`}
                aria-pressed={selected}
                onClick={(event) => {
                  event.stopPropagation()
                  onSelect(asset.assetId)
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault()
                    onSelect(asset.assetId)
                  }
                }}
              >
                <circle
                  r={selected ? 7 : 5}
                  fill={STATUS_FILL[status]}
                  stroke={selected ? "var(--foreground)" : "color-mix(in oklab, var(--background) 70%, transparent)"}
                  strokeWidth={selected ? 2 : 1}
                />
              </g>
            )
          })}
        </g>
      </svg>
    </div>
  )
}
