import { apiFetch } from "@/shared/api/http"

const PAGE = 500
const CACHE_MS = 15_000

type CacheEntry = { at: number; pages: unknown[][] }

const cache = new Map<string, CacheEntry>()
const inflight = new Map<string, Promise<unknown[][]>>()

function cacheKey(horizon: number, snapshotId?: string | null) {
  return `${snapshotId ?? "anon"}:${horizon}`
}

async function fetchPages(horizon: number): Promise<unknown[][]> {
  const pages: unknown[][] = []
  for (let offset = 0; offset < 100_000; offset += PAGE) {
    const page = await apiFetch<unknown[]>(
      `/api/v1/predictions?horizon=${horizon}&sort=risk_desc&limit=${PAGE}&offset=${offset}`
    )
    pages.push(page)
    if (page.length < PAGE) break
  }
  return pages
}

export async function loadHorizonPages(horizon: number, snapshotId?: string | null): Promise<unknown[][]> {
  const key = cacheKey(horizon, snapshotId)
  const now = Date.now()
  const hit = cache.get(key)
  if (hit && now - hit.at < CACHE_MS) return hit.pages

  const pending = inflight.get(key)
  if (pending) return pending

  const promise = fetchPages(horizon)
    .then((pages) => {
      cache.set(key, { at: Date.now(), pages })
      return pages
    })
    .finally(() => {
      inflight.delete(key)
    })
  inflight.set(key, promise)
  return promise
}

export function flattenHorizonPages(pages: unknown[][]): unknown[] {
  return pages.flat()
}

export function invalidateHorizonPages(horizon?: number) {
  if (horizon === undefined) {
    cache.clear()
    inflight.clear()
    return
  }
  for (const key of [...cache.keys()]) {
    if (key.endsWith(`:${horizon}`)) cache.delete(key)
  }
  for (const key of [...inflight.keys()]) {
    if (key.endsWith(`:${horizon}`)) inflight.delete(key)
  }
}
