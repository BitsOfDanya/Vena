import { describe, expect, it } from "vitest"

import { buildDemoSpatialCollection, extractMapGeometry, type SpatialCollection } from "./spatial-client"

const GENERATED: SpatialCollection = {
  type: "FeatureCollection",
  source: "generated",
  features: [
    {
      type: "Feature",
      id: "collector-7",
      geometry: {
        type: "MultiLineString",
        coordinates: [
          [
            [37.6, 55.7],
            [37.61, 55.71],
          ],
          [[37.62, 55.72]],
        ],
      },
      properties: { kind: "collector", object_id: "7", name: "Коллектор 7", source: "generated" },
    },
    {
      type: "Feature",
      geometry: {
        type: "LineString",
        coordinates: [
          [37.6, 55.7],
          [37.6, 55.705],
        ],
      },
      properties: { kind: "gallery", object_id: 7 },
    },
    {
      type: "Feature",
      id: 1234,
      geometry: { type: "Point", coordinates: [37.605, 55.705] },
      properties: { kind: "asset", object_id: "7", name: "Насос 1", source: "generated" },
    },
  ],
}

describe("extractMapGeometry", () => {
  it("reads generated collectors, galleries and channel points", () => {
    const geometry = extractMapGeometry(GENERATED)
    expect(geometry.generated).toBe(true)
    expect(geometry.lines).toEqual([
      {
        id: "collector-7",
        kind: "collector",
        name: "Коллектор 7",
        objectId: "7",
        paths: [
          [
            [37.6, 55.7],
            [37.61, 55.71],
          ],
        ],
      },
      {
        id: "gallery-1",
        kind: "gallery",
        name: undefined,
        objectId: "7",
        paths: [
          [
            [37.6, 55.7],
            [37.6, 55.705],
          ],
        ],
      },
    ])
    expect(geometry.assets).toEqual([
      { assetId: "1234", lon: 37.605, lat: 55.705, groupId: undefined, objectId: "7", name: "Насос 1" },
    ])
  })

  it("keeps the demo layer as points with a corridor", () => {
    const geometry = extractMapGeometry(buildDemoSpatialCollection())
    expect(geometry.generated).toBe(false)
    expect(geometry.lines).toEqual([])
    expect(geometry.corridor?.coordinates.length).toBe(16)
    expect(geometry.collectors).toHaveLength(16)
    expect(geometry.assets).toHaveLength(128)
  })
})
