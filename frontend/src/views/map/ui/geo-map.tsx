"use client"

import type { FeatureCollection, LineString, Point } from "geojson"
import { LocateFixed, Minus, Plus } from "lucide-react"
import { LngLatBounds, Map as LibreMap, setWorkerUrl, type GeoJSONSource } from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"
import { useEffect, useRef, useState } from "react"

import { Button } from "@/shared/ui/button"

import type { MapEdge, MapNode } from "../api/network"

const STYLE_URL = "https://tiles.openfreemap.org/styles/dark"
const EMPTY_POINTS: FeatureCollection<Point> = { type: "FeatureCollection", features: [] }
const EMPTY_LINES: FeatureCollection<LineString> = { type: "FeatureCollection", features: [] }

function pointFeatures(nodes: MapNode[]): FeatureCollection<Point> {
  return {
    type: "FeatureCollection",
    features: nodes.map((node) => ({
      type: "Feature",
      properties: {
        id: node.id,
        name: node.name,
        district: node.district,
        object_type: node.object_type,
        status: node.status,
      },
      geometry: { type: "Point", coordinates: [node.longitude, node.latitude] },
    })),
  }
}

function lineFeatures(nodes: MapNode[], edges: MapEdge[]): FeatureCollection<LineString> {
  const byId = new Map(nodes.map((node) => [node.id, node]))
  return {
    type: "FeatureCollection",
    features: edges.flatMap((edge) => {
      const source = byId.get(edge.source_id)
      const target = byId.get(edge.target_id)
      if (!source || !target) return []
      return [{
        type: "Feature" as const,
        properties: { id: edge.id, kind: edge.kind },
        geometry: {
          type: "LineString" as const,
          coordinates: [
            [source.longitude, source.latitude],
            [target.longitude, target.latitude],
          ],
        },
      }]
    }),
  }
}

function fitNetwork(map: LibreMap, nodes: MapNode[]) {
  if (nodes.length === 0) return
  const bounds = new LngLatBounds()
  for (const node of nodes) bounds.extend([node.longitude, node.latitude])
  map.fitBounds(bounds, { padding: 72, maxZoom: 12, duration: 700 })
}

export function GeoMap({ nodes, edges, selectedId, onSelect }: {
  nodes: MapNode[]
  edges: MapEdge[]
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<LibreMap | null>(null)
  const onSelectRef = useRef(onSelect)
  const fittedNodesRef = useRef<MapNode[] | null>(null)
  const [ready, setReady] = useState(false)
  const [styleError, setStyleError] = useState(false)

  useEffect(() => { onSelectRef.current = onSelect }, [onSelect])

  useEffect(() => {
    if (!containerRef.current) return
    const tokens = getComputedStyle(document.documentElement)
    const color = (name: string, fallback: string) => tokens.getPropertyValue(name).trim() || fallback
    const primary = color("--primary", "#4880ff")
    const normal = color("--status-normal", "#00b69b")
    const attention = color("--status-attention", "#ffbd62")
    const critical = color("--status-critical", "#ef6660")
    const background = color("--background", "#1b2431")
    const foreground = color("--foreground", "#f5f7fc")
    setWorkerUrl("/maplibre/maplibre-gl-worker.mjs")
    const map = new LibreMap({
      container: containerRef.current,
      style: STYLE_URL,
      center: [37.6173, 55.7558],
      zoom: 9.5,
      minZoom: 8,
      maxZoom: 17,
      renderWorldCopies: false,
    })
    mapRef.current = map
    map.on("load", () => {
      map.addSource("network-lines", { type: "geojson", data: EMPTY_LINES })
      map.addSource("network-points", { type: "geojson", data: EMPTY_POINTS })
      map.addSource("network-selected", { type: "geojson", data: EMPTY_POINTS })

      map.addLayer({
        id: "network-line-glow", type: "line", source: "network-lines",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": primary, "line-width": 10, "line-opacity": 0.13, "line-blur": 5 },
      })
      map.addLayer({
        id: "network-lines", type: "line", source: "network-lines",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": ["match", ["get", "kind"], "backbone", primary, "collector", normal, primary],
          "line-width": ["match", ["get", "kind"], "backbone", 3.5, "collector", 2.5, 1.7],
          "line-opacity": 0.75,
        },
      })
      map.addLayer({
        id: "node-halos", type: "circle", source: "network-points",
        filter: ["in", ["get", "status"], ["literal", ["critical", "attention"]]],
        paint: {
          "circle-color": ["match", ["get", "status"], "critical", critical, attention],
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 12, 13, 22],
          "circle-opacity": 0.2,
          "circle-blur": 0.65,
        },
      })
      map.addLayer({
        id: "node-points", type: "circle", source: "network-points",
        paint: {
          "circle-color": [
            "case",
            ["==", ["get", "status"], "critical"], critical,
            ["==", ["get", "status"], "attention"], attention,
            ["==", ["get", "object_type"], "hub"], primary,
            normal,
          ],
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 5, 13, 9],
          "circle-stroke-color": background,
          "circle-stroke-width": 2,
          "circle-opacity": 0.96,
        },
      })
      map.addLayer({
        id: "node-selected", type: "circle", source: "network-selected",
        paint: {
          "circle-color": primary,
          "circle-opacity": 0.16,
          "circle-radius": 18,
          "circle-stroke-color": foreground,
          "circle-stroke-width": 2,
        },
      })
      map.on("click", "node-points", (event) => {
        const id = event.features?.[0]?.properties?.id
        if (typeof id === "string") onSelectRef.current(id)
      })
      map.on("mouseenter", "node-points", () => { map.getCanvas().style.cursor = "pointer" })
      map.on("mouseleave", "node-points", () => { map.getCanvas().style.cursor = "" })
      setReady(true)
    })
    map.on("error", () => {
      if (!map.isStyleLoaded()) setStyleError(true)
    })
    return () => { map.remove(); mapRef.current = null }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    ;(map.getSource("network-points") as GeoJSONSource).setData(pointFeatures(nodes))
    ;(map.getSource("network-lines") as GeoJSONSource).setData(lineFeatures(nodes, edges))
    if (nodes.length && fittedNodesRef.current !== nodes) {
      fittedNodesRef.current = nodes
      fitNetwork(map, nodes)
    }
  }, [nodes, edges, ready])

  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    const node = nodes.find((item) => item.id === selectedId)
    ;(map.getSource("network-selected") as GeoJSONSource).setData(
      node ? pointFeatures([node]) : EMPTY_POINTS
    )
    if (node) map.flyTo({ center: [node.longitude, node.latitude], zoom: Math.max(map.getZoom(), 12), duration: 700 })
  }, [nodes, ready, selectedId])

  return (
    <div className="relative h-full min-h-[480px] overflow-hidden rounded-2xl border border-border bg-background">
      <div ref={containerRef} className="absolute inset-0" style={{ position: "absolute" }} aria-label="Карта Москвы с объектами и линиями сети" role="application" />
      <div className="absolute left-4 top-4 rounded-xl border border-white/10 bg-background/90 px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-white shadow-lg backdrop-blur">Москва · демонстрационная сеть</div>
      <div className="absolute right-4 top-4 flex flex-col gap-2">
        <Button variant="secondary" size="icon" aria-label="Приблизить карту" onClick={() => mapRef.current?.zoomIn()}><Plus className="size-4" /></Button>
        <Button variant="secondary" size="icon" aria-label="Отдалить карту" onClick={() => mapRef.current?.zoomOut()}><Minus className="size-4" /></Button>
        <Button variant="secondary" size="icon" aria-label="Показать всю сеть" onClick={() => mapRef.current && fitNetwork(mapRef.current, nodes)}><LocateFixed className="size-4" /></Button>
      </div>
      {styleError && <div className="absolute bottom-10 left-4 rounded-lg border border-destructive/40 bg-background/90 px-3 py-2 text-xs text-destructive">Картографическая подложка недоступна. Проверьте подключение к интернету.</div>}
    </div>
  )
}
