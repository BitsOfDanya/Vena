import { afterEach, describe, expect, it, vi } from "vitest"

import { apiActionRepository } from "./api-repository"

const action = {
  id: "A-1101",
  asset_id: "P-0142",
  source: "vena_forecast",
  source_detail: "Pump72",
  source_pattern_id: null,
  kind: "inspect",
  reason: "rising event rate",
  priority: "high",
  window_start: "2026-09-21T20:00:00Z",
  recommended_at: "2026-09-22T20:00:00Z",
  status: "suggested",
  assignee: "Бригада А",
  note: "",
  notify_channels: ["in_app"],
  created_by: "VENA",
  created_at: "2026-09-21T19:00:00Z",
  updated_at: "2026-09-21T19:00:00Z",
  result_outcome: null,
  result_note: "",
  completed_at: null,
  history: [{ event_type: "suggested", actor: "VENA", at: "2026-09-21T19:00:00Z", from_status: null, to_status: null, note: "" }],
}

function mockFetch(handler: (url: string, init?: RequestInit) => { status?: number; body: unknown }) {
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    const { status = 200, body } = handler(url, init)
    return { ok: status < 400, status, statusText: "", json: async () => body } as Response
  })
  return calls
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("api action repository", () => {
  it("maps a suggested action with history", async () => {
    mockFetch(() => ({ body: [action] }))

    const [item] = await apiActionRepository.list()

    expect(item.status).toBe("suggested")
    expect(item.source).toBe("vena_forecast")
    expect(item.history[0].type).toBe("suggested")
    expect(item.notifyChannels).toEqual(["in_app"])
  })

  it("approves through the dedicated command endpoint", async () => {
    const calls = mockFetch(() => ({ body: { ...action, status: "planned" } }))

    const approved = await apiActionRepository.approve("A-1101", Date.now())

    expect(calls[0].url).toContain("/api/v1/actions/A-1101/approve")
    expect(calls[0].init?.method).toBe("POST")
    expect(approved.status).toBe("planned")
  })

  it("records a result and maps the outcome name", async () => {
    const calls = mockFetch(() => ({
      body: { ...action, status: "completed", result_outcome: "false_or_irrelevant_signal", completed_at: "2026-09-22T06:00:00Z" },
    }))

    const completed = await apiActionRepository.close(
      { id: "A-1101", outcome: "false_signal", note: "checked" },
      Date.now()
    )

    expect(calls[0].url).toContain("/result")
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ outcome: "false_or_irrelevant_signal", note: "checked" })
    expect(completed.result?.outcome).toBe("false_signal")
  })

  it("rejects unsupported transitions instead of faking them", async () => {
    mockFetch(() => ({ body: action }))

    await expect(apiActionRepository.setStatus("A-1101", "suggested", Date.now())).rejects.toThrow(
      "Unsupported transition"
    )
  })
})
