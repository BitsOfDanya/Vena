import { describe, expect, it } from "vitest"

import { modelLabel } from "./model-label"

describe("modelLabel", () => {
  it("names channel models by scenario and horizon", () => {
    expect(modelLabel("phase_24h")).toBe("Питание, сутки")
    expect(modelLabel("pump_72h")).toBe("Подтопление, 3 суток")
  })

  it("names object models explicitly", () => {
    expect(modelLabel("object_flood_6h")).toBe("Подтопление станции, 6 ч")
    expect(modelLabel("object_fire_24h")).toBe("Пожар на объекте, сутки")
    expect(modelLabel(null)).toBe("—")
  })
})
