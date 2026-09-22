"use client"

import * as React from "react"

import { DEMO_NOW, type ForecastHorizon, type ReplayEpisode } from "@/entities/infrastructure"

export const REPLAY_SPEEDS = [1, 2, 4, 8] as const
export type ReplaySpeed = (typeof REPLAY_SPEEDS)[number]

const REPLAY_SECONDS_PER_SECOND = 120
const TICK_MS = 200
const MAX_COMPARE = 5

type ReplayState = {
  episode: ReplayEpisode
  time: number
  playing: boolean
  speed: ReplaySpeed
}

export type State = {
  selectedAssetId: string | null
  compareIds: string[]
  horizon: ForecastHorizon
  replay: ReplayState | null
}

export type Action =
  | { type: "select"; id: string | null }
  | { type: "toggle-compare"; id: string }
  | { type: "set-compare"; ids: string[] }
  | { type: "horizon"; horizon: ForecastHorizon }
  | { type: "replay-start"; episode: ReplayEpisode }
  | { type: "replay-stop" }
  | { type: "replay-seek"; time: number }
  | { type: "replay-toggle" }
  | { type: "replay-speed"; speed: ReplaySpeed }
  | { type: "replay-tick" }

export const INITIAL: State = {
  selectedAssetId: null,
  compareIds: [],
  horizon: 72,
  replay: null,
}

export function reduce(state: State, action: Action): State {
  switch (action.type) {
    case "select":
      return { ...state, selectedAssetId: action.id }
    case "toggle-compare": {
      const exists = state.compareIds.includes(action.id)
      const compareIds = exists
        ? state.compareIds.filter((id) => id !== action.id)
        : [...state.compareIds, action.id].slice(-MAX_COMPARE)
      return { ...state, compareIds }
    }
    case "set-compare":
      return { ...state, compareIds: action.ids.slice(0, MAX_COMPARE) }
    case "horizon":
      return { ...state, horizon: action.horizon }
    case "replay-start":
      return {
        ...state,
        selectedAssetId: action.episode.assetId,
        compareIds: [action.episode.assetId],
        replay: { episode: action.episode, time: action.episode.start, playing: true, speed: 1 },
      }
    case "replay-stop":
      return { ...state, replay: null }
    case "replay-seek":
      return state.replay
        ? {
            ...state,
            replay: {
              ...state.replay,
              time: Math.min(state.replay.episode.end, Math.max(state.replay.episode.start, action.time)),
            },
          }
        : state
    case "replay-toggle":
      if (!state.replay) return state
      return {
        ...state,
        replay: {
          ...state.replay,
          playing: !state.replay.playing,
          time: state.replay.time >= state.replay.episode.end ? state.replay.episode.start : state.replay.time,
        },
      }
    case "replay-speed":
      return state.replay ? { ...state, replay: { ...state.replay, speed: action.speed } } : state
    case "replay-tick": {
      if (!state.replay || !state.replay.playing) return state
      const next = state.replay.time + state.replay.speed * REPLAY_SECONDS_PER_SECOND * (TICK_MS / 1000) * 1000
      const finished = next >= state.replay.episode.end
      return {
        ...state,
        replay: { ...state.replay, time: finished ? state.replay.episode.end : next, playing: !finished },
      }
    }
  }
}

type Workspace = {
  now: number
  mode: "demo" | "replay"
  selectedAssetId: string | null
  compareIds: string[]
  horizon: ForecastHorizon
  replay: ReplayState | null
  selectAsset: (id: string | null) => void
  toggleCompare: (id: string) => void
  setCompare: (ids: string[]) => void
  setHorizon: (horizon: ForecastHorizon) => void
  startReplay: (episode: ReplayEpisode) => void
  stopReplay: () => void
  seekReplay: (time: number) => void
  toggleReplay: () => void
  setReplaySpeed: (speed: ReplaySpeed) => void
}

const WorkspaceContext = React.createContext<Workspace | null>(null)

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = React.useReducer(reduce, INITIAL)
  const playing = state.replay?.playing ?? false

  React.useEffect(() => {
    if (!playing) return
    const timer = window.setInterval(() => dispatch({ type: "replay-tick" }), TICK_MS)
    return () => window.clearInterval(timer)
  }, [playing])

  const value = React.useMemo<Workspace>(
    () => ({
      now: state.replay ? state.replay.time : DEMO_NOW,
      mode: state.replay ? "replay" : "demo",
      selectedAssetId: state.selectedAssetId,
      compareIds: state.compareIds,
      horizon: state.horizon,
      replay: state.replay,
      selectAsset: (id) => dispatch({ type: "select", id }),
      toggleCompare: (id) => dispatch({ type: "toggle-compare", id }),
      setCompare: (ids) => dispatch({ type: "set-compare", ids }),
      setHorizon: (horizon) => dispatch({ type: "horizon", horizon }),
      startReplay: (episode) => dispatch({ type: "replay-start", episode }),
      stopReplay: () => dispatch({ type: "replay-stop" }),
      seekReplay: (time) => dispatch({ type: "replay-seek", time }),
      toggleReplay: () => dispatch({ type: "replay-toggle" }),
      setReplaySpeed: (speed) => dispatch({ type: "replay-speed", speed }),
    }),
    [state]
  )

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>
}

export function useWorkspace() {
  const context = React.useContext(WorkspaceContext)
  if (!context) throw new Error("useWorkspace must be used inside WorkspaceProvider")
  return context
}
