import type { AssetType, NetworkEdge } from "../model/types"

export const CANVAS_WIDTH = 1720
export const CANVAS_HEIGHT = 1120

const COLUMNS = 4
const CELL_WIDTH = CANVAS_WIDTH / COLUMNS
const CELL_HEIGHT = CANVAS_HEIGHT / 4
const CELL_PAD_X = 56
const BRANCH_GAP = 40

export type LayoutInput = {
  groupIndex: number
  groupId: string
  assets: { id: string; type: AssetType }[]
}

export type LayoutResult = {
  positions: Map<string, { x: number; y: number }>
  groupOrigins: Map<string, { x: number; y: number }>
  edges: NetworkEdge[]
  hubs: Map<string, string>
}

const TRUNK_TYPES: AssetType[] = ["pump", "fan", "power"]

export function layoutGroups(inputs: LayoutInput[]): LayoutResult {
  const positions = new Map<string, { x: number; y: number }>()
  const groupOrigins = new Map<string, { x: number; y: number }>()
  const edges: NetworkEdge[] = []
  const hubs = new Map<string, string>()

  for (const input of inputs) {
    const column = input.groupIndex % COLUMNS
    const row = Math.floor(input.groupIndex / COLUMNS)
    const left = column * CELL_WIDTH + CELL_PAD_X
    const trunkY = row * CELL_HEIGHT + CELL_HEIGHT / 2 + 8
    groupOrigins.set(input.groupId, { x: left, y: row * CELL_HEIGHT + 36 })

    const trunk = input.assets.filter((asset) => TRUNK_TYPES.includes(asset.type))
    const branches = input.assets.filter((asset) => !TRUNK_TYPES.includes(asset.type))
    const anchors = trunk.length > 0 ? trunk : branches.splice(0, 1)
    const span = CELL_WIDTH - CELL_PAD_X * 2 - 24
    const step = anchors.length > 1 ? Math.min(72, span / (anchors.length - 1)) : 0

    anchors.forEach((asset, index) => {
      positions.set(asset.id, { x: left + 18 + index * step, y: trunkY })
      if (index > 0) {
        edges.push({ source: anchors[index - 1].id, target: asset.id, relationType: "group" })
      }
    })
    if (anchors.length > 0) hubs.set(input.groupId, anchors[0].id)

    const levelUse = new Map<string, number>()
    branches.forEach((asset, index) => {
      const anchorIndex = index % anchors.length
      const anchor = anchors[anchorIndex]
      const direction = index % 2 === 0 ? -1 : 1
      const key = `${anchorIndex}:${direction}`
      const level = (levelUse.get(key) ?? 0) + 1
      levelUse.set(key, level)
      const base = positions.get(anchor.id)
      if (!base) return
      positions.set(asset.id, { x: base.x, y: base.y + direction * level * BRANCH_GAP })
      const parentId = level === 1 ? anchor.id : (levelPeer(branches, index, anchors.length) ?? anchor.id)
      edges.push({ source: parentId, target: asset.id, relationType: "group" })
    })
  }

  return { positions, groupOrigins, edges, hubs }
}

function levelPeer(branches: { id: string }[], index: number, anchorCount: number) {
  const peerIndex = index - anchorCount * 2
  return peerIndex >= 0 ? branches[peerIndex]?.id : undefined
}
