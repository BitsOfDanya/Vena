import { z } from "zod"

import { apiFetch } from "@/shared/api/http"

const nodeSchema = z.object({
  id: z.string(),
  name: z.string(),
  district: z.string(),
  object_type: z.string(),
  status: z.string(),
  latitude: z.number(),
  longitude: z.number(),
  is_demo: z.boolean(),
})

const edgeSchema = z.object({
  id: z.string(),
  source_id: z.string(),
  target_id: z.string(),
  kind: z.string(),
  is_demo: z.boolean(),
})

const networkSchema = z.object({
  nodes: z.array(nodeSchema),
  edges: z.array(edgeSchema),
})

export type MapNode = z.infer<typeof nodeSchema>
export type MapEdge = z.infer<typeof edgeSchema>
export type MapNetwork = z.infer<typeof networkSchema>

export async function getMapNetwork(): Promise<MapNetwork> {
  return networkSchema.parse(await apiFetch<unknown>("/api/v1/map/network"))
}
