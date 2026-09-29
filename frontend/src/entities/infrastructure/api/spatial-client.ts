import { z } from "zod"

import { apiFetch } from "@/shared/api/http"
import { workflowMode } from "@/shared/config/env"

const FeatureSchema = z.object({
  type: z.literal("Feature"),
  id: z.union([z.string(), z.number()]).optional(),
  geometry: z.object({
    type: z.string(),
    coordinates: z.unknown(),
  }),
  properties: z.record(z.string(), z.unknown()).optional(),
})

const CollectionSchema = z.object({
  type: z.literal("FeatureCollection"),
  features: z.array(FeatureSchema),
  properties: z.record(z.string(), z.unknown()).optional(),
  source: z.string().optional(),
  updated_at: z.string().nullable().optional(),
})

const StatusSchema = z.object({
  configured: z.boolean(),
  source: z.string().nullable().optional(),
  feature_count: z.number(),
  asset_count: z.number(),
  updated_at: z.string().nullable().optional(),
})

export type SpatialFeature = z.infer<typeof FeatureSchema>
export type SpatialCollection = z.infer<typeof CollectionSchema>
export type SpatialStatus = z.infer<typeof StatusSchema>

export type MapAssetPoint = {
  assetId: string
  lon: number
  lat: number
  groupId?: string
  name?: string
}

export type MapCorridor = {
  coordinates: [number, number][]
}

function asLonLat(coordinates: unknown): [number, number] | null {
  if (!Array.isArray(coordinates) || coordinates.length < 2) return null
  const lon = Number(coordinates[0])
  const lat = Number(coordinates[1])
  if (!Number.isFinite(lon) || !Number.isFinite(lat)) return null
  return [lon, lat]
}

export function extractMapGeometry(collection: SpatialCollection): {
  assets: MapAssetPoint[]
  corridor: MapCorridor | null
  collectors: MapAssetPoint[]
} {
  const assets: MapAssetPoint[] = []
  const collectors: MapAssetPoint[] = []
  let corridor: MapCorridor | null = null

  for (const feature of collection.features) {
    const props = feature.properties ?? {}
    const kind = typeof props.kind === "string" ? props.kind : ""
    if (feature.geometry.type === "Point") {
      const pair = asLonLat(feature.geometry.coordinates)
      if (!pair) continue
      const [lon, lat] = pair
      const assetId = typeof props.asset_id === "string" ? props.asset_id : String(feature.id ?? "")
      const point = {
        assetId,
        lon,
        lat,
        groupId: typeof props.group_id === "string" ? props.group_id : undefined,
        name: typeof props.name === "string" ? props.name : undefined,
      }
      if (kind === "collector") collectors.push(point)
      else if (kind === "asset" || assetId) assets.push(point)
    }
    if (feature.geometry.type === "LineString" && kind === "corridor") {
      const raw = feature.geometry.coordinates
      if (Array.isArray(raw)) {
        const coordinates = raw
          .map((item) => asLonLat(item))
          .filter((item): item is [number, number] => item !== null)
        if (coordinates.length >= 2) corridor = { coordinates }
      }
    }
  }

  return { assets, corridor, collectors }
}

export function buildDemoSpatialCollection(): SpatialCollection {
  const ORIGIN_LON = 37.635
  const ORIGIN_LAT = 55.748
  const GROUP_STEP_LON = 0.0042
  const GROUP_STEP_LAT = -0.0031
  const ASSET_SPREAD = 0.00055
  const TYPES = ["pump", "fan", "smoke", "power", "other"] as const
  const features: SpatialFeature[] = []
  const corridor: [number, number][] = []

  for (let groupIndex = 0; groupIndex < 16; groupIndex += 1) {
    const gx = ORIGIN_LON + (groupIndex % 4) * GROUP_STEP_LON * 2.2
    const gy = ORIGIN_LAT + Math.floor(groupIndex / 4) * GROUP_STEP_LAT
    corridor.push([Number(gx.toFixed(6)), Number(gy.toFixed(6))])
    const groupId = `K-${String(groupIndex + 1).padStart(2, "0")}`
    features.push({
      type: "Feature",
      id: `group-${groupId}`,
      geometry: { type: "Point", coordinates: [Number(gx.toFixed(6)), Number(gy.toFixed(6))] },
      properties: { kind: "collector", group_id: groupId, name: `Коллектор К${groupIndex + 1}`, source: "demo_spatial" },
    })
  }

  features.unshift({
    type: "Feature",
    id: "corridor-main",
    geometry: { type: "LineString", coordinates: corridor },
    properties: { kind: "corridor", name: "Demo collector corridor", source: "demo_spatial" },
  })

  for (let index = 0; index < 128; index += 1) {
    const groupIndex = Math.floor(index / 8)
    const gx = ORIGIN_LON + (groupIndex % 4) * GROUP_STEP_LON * 2.2
    const gy = ORIGIN_LAT + Math.floor(groupIndex / 4) * GROUP_STEP_LAT
    const angle = (index % 8) * ((2 * Math.PI) / 8)
    const lon = gx + Math.cos(angle) * ASSET_SPREAD
    const lat = gy + Math.sin(angle) * ASSET_SPREAD * 0.7
    const assetType = TYPES[index % TYPES.length]
    const assetId = index === 0 ? "P-0142" : `${assetType[0].toUpperCase()}-${String(index + 101).padStart(4, "0")}`
    features.push({
      type: "Feature",
      id: assetId,
      geometry: { type: "Point", coordinates: [Number(lon.toFixed(6)), Number(lat.toFixed(6))] },
      properties: {
        kind: "asset",
        asset_id: assetId,
        group_id: `K-${String(groupIndex + 1).padStart(2, "0")}`,
        asset_type: assetType,
        name: `${assetType} ${index + 1}`,
        source: "demo_spatial",
      },
    })
  }

  return {
    type: "FeatureCollection",
    features,
    properties: { source: "demo_spatial", crs: "EPSG:4326" },
    source: "demo_spatial",
  }
}

export async function getSpatialStatus(): Promise<SpatialStatus> {
  if (workflowMode !== "api") {
    const demo = buildDemoSpatialCollection()
    const geometry = extractMapGeometry(demo)
    return {
      configured: true,
      source: "demo_spatial",
      feature_count: demo.features.length,
      asset_count: geometry.assets.length,
      updated_at: null,
    }
  }
  const raw = await apiFetch<unknown>("/api/v1/spatial/status")
  return StatusSchema.parse(raw)
}

export async function getSpatialCollection(): Promise<SpatialCollection> {
  if (workflowMode !== "api") {
    return buildDemoSpatialCollection()
  }
  try {
    const raw = await apiFetch<unknown>("/api/v1/spatial")
    return CollectionSchema.parse(raw)
  } catch {
    return buildDemoSpatialCollection()
  }
}
