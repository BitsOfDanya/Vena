import { afterEach, describe, expect, it, vi } from "vitest"

import { apiNotificationRepository, getApiSystemNotices } from "./api-repository"

type FetchArgs = { url: string; init?: RequestInit }

function mockFetch(handler: (args: FetchArgs) => { status?: number; body: unknown }) {
  const calls: FetchArgs[] = []
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    const args = { url, init }
    calls.push(args)
    const { status = 200, body } = handler(args)
    return {
      ok: status < 400,
      status,
      statusText: "",
      json: async () => body,
    } as Response
  })
  return calls
}

const notification = {
  id: "N-1",
  type: "risk",
  severity: "attention",
  title: "P-0142 risk",
  description: "rising",
  asset_id: "P-0142",
  pattern_id: null,
  action_id: null,
  created_at: "2026-09-21T20:00:00Z",
  status: "new",
  read_at: null,
  acknowledged_at: null,
  resolved_at: null,
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("api notification repository", () => {
  it("maps backend severity and timestamps", async () => {
    mockFetch(() => ({ body: [notification] }))

    const [item] = await apiNotificationRepository.list()

    expect(item.severity).toBe("warning")
    expect(item.assetId).toBe("P-0142")
    expect(item.createdAt).toBe(Date.parse("2026-09-21T20:00:00Z"))
    expect(item.readAt).toBeNull()
  })

  it("acknowledges through the API and re-reads the list", async () => {
    const calls = mockFetch(({ init }) =>
      init?.method === "PATCH"
        ? { body: { ...notification, status: "acknowledged" } }
        : { body: [{ ...notification, status: "acknowledged", acknowledged_at: "2026-09-21T20:05:00Z" }] }
    )

    const [item] = await apiNotificationRepository.acknowledge("N-1", Date.now())

    expect(calls[0].init?.method).toBe("PATCH")
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ status: "acknowledged" })
    expect(item.status).toBe("acknowledged")
    expect(item.acknowledgedAt).not.toBeNull()
  })

  it("surfaces API errors instead of pretending success", async () => {
    mockFetch(() => ({ status: 409, body: { detail: "new -> acknowledged" } }))

    await expect(apiNotificationRepository.acknowledge("N-1", Date.now())).rejects.toMatchObject({
      status: 409,
      detail: "new -> acknowledged",
    })
  })

  it("returns an empty notice list when the backend reports no problems", async () => {
    mockFetch(() => ({ body: [] }))

    await expect(getApiSystemNotices()).resolves.toEqual([])
  })
})
