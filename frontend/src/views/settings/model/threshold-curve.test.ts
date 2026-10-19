import { describe, expect, it } from "vitest"

import { nearestIndex, pointAt, sameLevels, sliderSteps, withLevel, type CurvePoint } from "./threshold-curve"

const point = (threshold: number, precision: number | null = null): CurvePoint => ({
  threshold,
  probability: null,
  precision,
  recall: null,
  channels_per_day: null,
})

const curve = [point(0.2, 0.1), point(0.5, 0.3), point(0.8, 0.6), point(0.95, 0.9)]

describe("threshold curve", () => {
  it("moves the slider along the curve points", () => {
    expect(sliderSteps(curve)).toEqual([0.2, 0.5, 0.8, 0.95])
    expect(sliderSteps([point(0), point(0.4), point(1.2)])).toEqual([0.4])
  })

  it("falls back to an even scale when the curve is not computed", () => {
    const steps = sliderSteps([])
    expect(steps).toHaveLength(200)
    expect(steps[0]).toBeCloseTo(0.005)
    expect(steps.at(-1)).toBe(1)
  })

  it("finds the nearest point for any threshold", () => {
    const steps = sliderSteps(curve)
    expect(nearestIndex(steps, 0.1)).toBe(0)
    expect(nearestIndex(steps, 0.64)).toBe(1)
    expect(nearestIndex(steps, 0.66)).toBe(2)
    expect(nearestIndex(steps, 0.8)).toBe(2)
    expect(nearestIndex(steps, 0.99)).toBe(3)
    expect(nearestIndex([], 0.5)).toBe(-1)
  })

  it("reads metrics of the nearest point", () => {
    expect(pointAt(curve, 0.93)?.precision).toBe(0.9)
    expect(pointAt(curve, 0.3)?.threshold).toBe(0.2)
    expect(pointAt([], 0.3)).toBeNull()
  })

  it("keeps critical ≥ high ≥ medium while a level moves", () => {
    const levels = { critical: 0.95, high: 0.8, medium: 0.5 }
    expect(withLevel(levels, "high", 0.99)).toEqual({ critical: 0.95, high: 0.95, medium: 0.5 })
    expect(withLevel(levels, "high", 0.2)).toEqual({ critical: 0.95, high: 0.5, medium: 0.5 })
    expect(withLevel(levels, "critical", 0.6)).toEqual({ critical: 0.8, high: 0.8, medium: 0.5 })
    expect(withLevel(levels, "medium", 0.9)).toEqual({ critical: 0.95, high: 0.8, medium: 0.8 })
    expect(withLevel(levels, "high", 0.85)).toEqual({ critical: 0.95, high: 0.85, medium: 0.5 })
  })

  it("compares threshold sets", () => {
    expect(sameLevels({ critical: 0.9, high: 0.8, medium: 0.5 }, { critical: 0.9, high: 0.8, medium: 0.5 })).toBe(true)
    expect(sameLevels({ critical: 0.9, high: 0.8, medium: 0.5 }, { critical: 0.9, high: 0.7, medium: 0.5 })).toBe(false)
    expect(sameLevels(null, null)).toBe(true)
  })
})
