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
