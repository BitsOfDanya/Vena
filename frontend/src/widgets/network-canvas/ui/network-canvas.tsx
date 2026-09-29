"use client"

import { Maximize, Minus, Plus } from "lucide-react"
import * as React from "react"

import { RISK_HIGH, RISK_MEDIUM, StatusMark, type NetworkEdge, type NetworkModel, type NetworkNode } from "@/entities/infrastructure"
import { useElementSize } from "@/shared/lib/hooks/use-element-size"
import { useReducedMotion } from "@/shared/lib/hooks/use-reduced-motion"
import { cn } from "@/shared/lib/utils"
import { Button } from "@/shared/ui/button"

type Transform = { k: number; x: number; y: number }

const STATUS_STROKE = {
  normal: "stroke-status-normal",
  attention: "stroke-status-attention",
  critical: "stroke-status-critical",
  offline: "stroke-status-offline",
} as const

const STATUS_FILL = {
  normal: "fill-status-normal",
  attention: "fill-status-attention",
  critical: "fill-status-critical",
  offline: "fill-status-offline",
} as const

const MIN_ZOOM = 0.4
const MAX_ZOOM = 5
const LABEL_ZOOM = 1.6

function edgePath(edge: NetworkEdge, nodes: Map<string, NetworkNode>) {
  const source = nodes.get(edge.source)
  const target = nodes.get(edge.target)
  if (!source || !target) return null
  if (source.x === target.x || source.y === target.y) return `M${source.x} ${source.y} L${target.x} ${target.y}`
  const middle = (source.x + target.x) / 2
  return `M${source.x} ${source.y} H${middle} V${target.y} H${target.x}`
}

function diamond(x: number, y: number, half: number) {
  return `M${x} ${y - half} L${x + half} ${y} L${x} ${y + half} L${x - half} ${y} Z`
}

function nodeRadius(node: NetworkNode) {
  return 4.6 + (node.risk / 100) * 4
}

type Props = {
  model: NetworkModel
  selectedId: string | null
  dimmed: Set<string>
  pulseAssetId: string | null
  onSelect: (id: string | null) => void
  focusId?: string | null
}

export function NetworkCanvas({ model, selectedId, dimmed, pulseAssetId, onSelect, focusId }: Props) {
  const [containerRef, size] = useElementSize<HTMLDivElement>()
  const reducedMotion = useReducedMotion()
  const [transform, setTransform] = React.useState<Transform>({ k: 1, x: 0, y: 0 })
  const [hoverId, setHoverId] = React.useState<string | null>(null)
  const drag = React.useRef<{ x: number; y: number; moved: boolean } | null>(null)
  const touched = React.useRef(false)
  const svgRef = React.useRef<SVGSVGElement | null>(null)

  const nodes = React.useMemo(() => new Map(model.nodes.map((node) => [node.id, node])), [model.nodes])
  const edges = React.useMemo(
    () => model.edges.map((edge) => ({ edge, path: edgePath(edge, nodes) })).filter((item): item is { edge: NetworkEdge; path: string } => item.path !== null),
    [model.edges, nodes]
  )

  const fit = React.useCallback(() => {
    if (size.width === 0 || size.height === 0) return
    const k = Math.min(size.width / model.width, size.height / model.height) * 0.98
    setTransform({ k, x: (size.width - model.width * k) / 2, y: (size.height - model.height * k) / 2 })
  }, [size.width, size.height, model.width, model.height])

  React.useEffect(() => {
    if (!touched.current && size.width > 0) fit()
  }, [fit, size.width])

  React.useEffect(() => {
    if (!focusId) return
    const node = nodes.get(focusId)
    if (!node || size.width === 0) return
    touched.current = true
    const frame = requestAnimationFrame(() =>
      setTransform((current) => {
        const k = Math.max(current.k, 1.7)
        return { k, x: size.width / 2 - node.x * k, y: size.height / 2 - node.y * k }
      })
    )
    return () => cancelAnimationFrame(frame)
  }, [focusId, nodes, size.width, size.height])

  React.useEffect(() => {
    const element = svgRef.current
    if (!element) return
    function onWheel(event: WheelEvent) {
      event.preventDefault()
      touched.current = true
      const rect = element!.getBoundingClientRect()
      const px = event.clientX - rect.left
      const py = event.clientY - rect.top
      setTransform((current) => {
        const k = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, current.k * Math.exp(-event.deltaY * 0.0015)))
        const ratio = k / current.k
        return { k, x: px - (px - current.x) * ratio, y: py - (py - current.y) * ratio }
      })
    }
    element.addEventListener("wheel", onWheel, { passive: false })
    return () => element.removeEventListener("wheel", onWheel)
  }, [])

  const zoomBy = (factor: number) => {
    touched.current = true
    setTransform((current) => {
      const k = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, current.k * factor))
      const cx = size.width / 2
      const cy = size.height / 2
      const ratio = k / current.k
      return { k, x: cx - (cx - current.x) * ratio, y: cy - (cy - current.y) * ratio }
    })
  }

  const pulsePaths = pulseAssetId
    ? edges.filter((item) => item.edge.target === pulseAssetId && item.edge.relationType === "group").slice(0, 1)
    : []
  const labelAll = transform.k >= LABEL_ZOOM

  return (
    <div ref={containerRef} className="relative size-full overflow-hidden bg-background">
      <svg
        ref={svgRef}
        width={size.width}
        height={size.height}
        role="group"
        aria-label="Schematic infrastructure network. Lines show logical grouping, not physical connections."
        className="block cursor-grab touch-none select-none active:cursor-grabbing"
        onPointerDown={(event) => {
          if (event.target !== event.currentTarget && !(event.target as Element).hasAttribute("data-canvas")) return
          drag.current = { x: event.clientX, y: event.clientY, moved: false }
          event.currentTarget.setPointerCapture(event.pointerId)
        }}
        onPointerMove={(event) => {
          if (!drag.current) return
          const dx = event.clientX - drag.current.x
          const dy = event.clientY - drag.current.y
          if (Math.abs(dx) + Math.abs(dy) > 2) {
            drag.current.moved = true
            touched.current = true
          }
          drag.current.x = event.clientX
          drag.current.y = event.clientY
          setTransform((current) => ({ ...current, x: current.x + dx, y: current.y + dy }))
        }}
        onPointerUp={(event) => {
          if (drag.current && !drag.current.moved) onSelect(null)
          drag.current = null
          event.currentTarget.releasePointerCapture(event.pointerId)
        }}
      >
        <rect data-canvas width={size.width} height={size.height} fill="transparent" />
        <g transform={`translate(${transform.x} ${transform.y}) scale(${transform.k})`}>
          {model.groups.map((group) => (
            <g key={group.id}>
              <line x1={group.x} x2={group.x + 340} y1={group.y + 8} y2={group.y + 8} className="stroke-foreground/25" strokeWidth={1} vectorEffect="non-scaling-stroke" />
              <line x1={group.x} x2={group.x} y1={group.y + 8} y2={group.y + 14} className="stroke-foreground/45" strokeWidth={1} vectorEffect="non-scaling-stroke" />
              <text x={group.x} y={group.y} className="fill-muted-foreground text-[12px] font-medium">
                {group.id}
                <tspan dx={6} className="fill-faint font-normal">
                  {group.system}
                </tspan>
              </text>
              {group.maxRisk >= RISK_MEDIUM ? (
                <path
                  d={diamond(group.x + 330, group.y - 3.5, 4)}
                  className={group.maxRisk >= RISK_HIGH ? "fill-status-critical" : "fill-background stroke-status-attention"}
                  strokeWidth={1.4}
                />
              ) : null}
            </g>
          ))}
          {edges.map(({ edge, path }) => (
            <path
              key={`${edge.source}-${edge.target}`}
              d={path}
              fill="none"
              className={cn("stroke-foreground/40", edge.relationType === "logical" && "stroke-foreground/25")}
              strokeWidth={edge.relationType === "logical" ? 1 : 1.2}
              strokeDasharray={edge.relationType === "logical" ? "5 5" : undefined}
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {!reducedMotion
            ? pulsePaths.map(({ edge, path }) => (
                <circle key={`pulse-${edge.target}-${pulseAssetId}`} r={2.6} className="fill-vena">
                  <animateMotion dur="1.4s" repeatCount="1" path={path} fill="freeze" />
                  <animate attributeName="opacity" values="1;1;0" dur="1.4s" repeatCount="1" fill="freeze" />
                </circle>
              ))
            : null}
          {model.nodes.map((node) => {
            const r = nodeRadius(node)
            const dim = dimmed.has(node.id)
            const selected = node.id === selectedId
            const hovered = node.id === hoverId
            const important = node.status === "critical" || node.status === "attention"
            const showLabel = selected || hovered || node.risk >= RISK_HIGH || (labelAll && !dim)
            return (
              <g
                key={node.id}
                role="button"
                tabIndex={important || selected ? 0 : -1}
                aria-label={`${node.id}, ${node.type}, ${node.status}, risk ${node.risk} of 100`}
                aria-pressed={selected}
                opacity={dim ? 0.22 : 1}
                className="cursor-pointer outline-none [&:focus-visible_circle.hit]:stroke-ring"
                onPointerEnter={() => setHoverId(node.id)}
                onPointerLeave={() => setHoverId((current) => (current === node.id ? null : current))}
                onFocus={() => setHoverId(node.id)}
                onBlur={() => setHoverId(null)}
                onPointerDown={(event) => event.stopPropagation()}
                onClick={(event) => {
                  event.stopPropagation()
                  onSelect(node.id)
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault()
                    onSelect(node.id)
                  }
                }}
              >
                <circle className="hit fill-transparent stroke-transparent" strokeWidth={1.5} cx={node.x} cy={node.y} r={r + 7} />
                {node.status === "critical" && !reducedMotion ? (
                  <circle cx={node.x} cy={node.y} r={r + 5} fill="none" className="vena-breathe stroke-status-critical" strokeWidth={1.2} />
                ) : null}
                {selected ? <path d={diamond(node.x, node.y, r * 1.3 + 6)} fill="none" className="stroke-vena" strokeWidth={1.6} /> : null}
                {node.status === "critical" ? <path d={diamond(node.x, node.y, r * 1.3 + 0.6)} className={STATUS_FILL.critical} /> : null}
                {node.status === "attention" ? (
                  <path d={diamond(node.x, node.y, r * 1.3)} className={cn("fill-background", STATUS_STROKE.attention)} strokeWidth={1.7} strokeLinejoin="miter" />
                ) : null}
                {node.status === "normal" ? (
                  <circle cx={node.x} cy={node.y} r={r} className={cn("fill-background", STATUS_STROKE.normal)} strokeWidth={1.4} />
                ) : null}
                {node.status === "offline" ? (
                  <circle cx={node.x} cy={node.y} r={r} className={cn("fill-background", STATUS_STROKE.offline)} strokeWidth={1.3} strokeDasharray="2 2" />
                ) : null}
                {hovered && !selected ? <circle cx={node.x} cy={node.y} r={r + 5} fill="none" className="stroke-muted-foreground" strokeWidth={1} /> : null}
                {showLabel ? (
                  <text x={node.x + r + 6} y={node.y + 3.5} className="fill-foreground font-mono text-[11px] tabular-nums" paintOrder="stroke" stroke="var(--background)" strokeWidth={3}>
                    {node.id}
                  </text>
                ) : null}
              </g>
            )
          })}
        </g>
      </svg>
      <div className="absolute bottom-3 left-3 flex flex-col gap-1">
        <Button variant="outline" size="icon-sm" aria-label="Увеличить" onClick={() => zoomBy(1.3)}>
          <Plus />
        </Button>
        <Button variant="outline" size="icon-sm" aria-label="Уменьшить" onClick={() => zoomBy(1 / 1.3)}>
          <Minus />
        </Button>
        <Button
          variant="outline"
          size="icon-sm"
          aria-label="Вписать в экран"
          onClick={() => {
            touched.current = false
            fit()
          }}
        >
          <Maximize />
        </Button>
      </div>
      <div className="pointer-events-none absolute right-4 bottom-4 flex flex-col gap-1.5 border-l bg-background/80 pl-3 text-[10px] font-medium text-muted-foreground">
        <span className="text-faint">Легенда</span>
        <span className="flex items-center gap-2"><StatusMark status="normal" />Норма</span>
        <span className="flex items-center gap-2"><StatusMark status="attention" />Внимание</span>
        <span className="flex items-center gap-2"><StatusMark status="critical" />Критично</span>
        <span className="flex items-center gap-2"><StatusMark status="offline" />Офлайн</span>
        <span className="mt-1 max-w-44 normal-case tracking-normal text-faint">Линии: логическая группировка, не физические связи.</span>
      </div>
    </div>
  )
}
