export function mulberry32(seed: number) {
  let state = seed >>> 0
  return function next() {
    state = (state + 0x6d2b79f5) >>> 0
    let t = state
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export function pick<T>(rng: () => number, items: readonly T[]): T {
  return items[Math.floor(rng() * items.length)]
}

export function shuffle<T>(rng: () => number, items: readonly T[]): T[] {
  const copy = [...items]
  for (let index = copy.length - 1; index > 0; index -= 1) {
    const other = Math.floor(rng() * (index + 1))
    const held = copy[index]
    copy[index] = copy[other]
    copy[other] = held
  }
  return copy
}

export function lowerBound<T>(items: readonly T[], value: number, key: (item: T) => number) {
  let low = 0
  let high = items.length
  while (low < high) {
    const middle = (low + high) >>> 1
    if (key(items[middle]) < value) low = middle + 1
    else high = middle
  }
  return low
}

export function upperBound<T>(items: readonly T[], value: number, key: (item: T) => number) {
  let low = 0
  let high = items.length
  while (low < high) {
    const middle = (low + high) >>> 1
    if (key(items[middle]) <= value) low = middle + 1
    else high = middle
  }
  return low
}
