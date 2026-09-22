import { describe, expect, it } from "vitest"

import { reduce, INITIAL, type Action } from "./workspace"

const episode = { id: "e", label: "Episode", assetId: "P-0142", start: 1_000_000, end: 9_000_000 }

function run(actions: Action[]) {
  return actions.reduce(reduce, INITIAL)
}

describe("workspace reducer", () => {
  it("starts replay on the episode asset and never runs past the end", () => {
    let state = run([{ type: "replay-start", episode }])
    expect(state.replay?.time).toBe(episode.start)
    expect(state.selectedAssetId).toBe("P-0142")
    for (let index = 0; index < 500; index += 1) state = reduce(state, { type: "replay-tick" })
    expect(state.replay?.time).toBe(episode.end)
    expect(state.replay?.playing).toBe(false)
  })

  it("clamps seeking to the episode window", () => {
    const state = run([{ type: "replay-start", episode }, { type: "replay-seek", time: 99_999_999 }])
    expect(state.replay?.time).toBe(episode.end)
    expect(run([{ type: "replay-start", episode }, { type: "replay-seek", time: 0 }]).replay?.time).toBe(episode.start)
  })

  it("caps compared assets at five and toggles membership", () => {
    const state = run(["a", "b", "c", "d", "e", "f"].map((id) => ({ type: "toggle-compare", id }) as Action))
    expect(state.compareIds).toEqual(["b", "c", "d", "e", "f"])
    expect(reduce(state, { type: "toggle-compare", id: "c" }).compareIds).not.toContain("c")
  })

  it("restarts from the beginning when toggling play after the end", () => {
    let state = run([{ type: "replay-start", episode }, { type: "replay-seek", time: episode.end }])
    state = reduce(state, { type: "replay-toggle" })
    expect(state.replay?.time).toBe(episode.start)
    expect(state.replay?.playing).toBe(false)
  })
})
