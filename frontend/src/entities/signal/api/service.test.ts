import { afterEach, describe, expect, it, vi } from "vitest"

import { getAccessEvents, getAlarms } from "./service"

afterEach(() => vi.unstubAllGlobals())

function respond(body: unknown) {
  vi.stubGlobal("fetch", async () => ({ ok: true, status: 200, statusText: "", json: async () => body }) as Response)
}

describe("signal service", () => {
  it("maps alarm assessments from the API", async () => {
    respond([
      {
        channel_id: "7",
        ts: "2026-06-30T18:08:25",
        sensor_type: "Датчик дыма",
        corroboration_probability: 0.72,
        needs_verification: true,
        location: "Объект 1051 · 1.1.916",
        name: "Дым ПК1137+7",
      },
    ])
    const [alarm] = await getAlarms()
    expect(alarm.needsVerification).toBe(true)
    expect(alarm.corroborationProbability).toBeCloseTo(0.72)
    expect(Number.isNaN(alarm.ts)).toBe(false)
  })

  it("rejects access events without an index", async () => {
    respond([{ channel_id: "9", ts: "2026-06-29T02:00:00", sensor_type: "КД Люк", object: "16" }])
    await expect(getAccessEvents()).rejects.toThrow()
  })
})
