import assert from "node:assert/strict"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { loginWithPassword, logoutSession, resolveSession } from "./auth-audit"

const fetchMock = vi.fn()
vi.stubGlobal("fetch", fetchMock)
const me = { subject: "user1", role: "dispatcher", auth_method: "jwt", email: "user1@example.com" }
function respond(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })
}
beforeEach(() => { fetchMock.mockReset() })
describe("password session", () => {
  it("sends credentials and uses the HttpOnly cookie", async () => {
    fetchMock.mockResolvedValue(respond({ access_token: "server-token", user: me }))
    expect(await loginWithPassword("user1", "0987654321")).toEqual(me)
    const [, init] = fetchMock.mock.calls[0]
    expect(init.credentials).toBe("include")
    expect(JSON.parse(init.body)).toEqual({ email: "user1", password: "0987654321" })
    expect(init.headers).not.toHaveProperty("X-API-Key")
  })
  it("restores a session after reload from the cookie", async () => {
    fetchMock.mockResolvedValueOnce(respond({ auth_enabled: true, methods: ["password"], configured: true }))
      .mockResolvedValueOnce(respond(me))
    expect((await resolveSession()).me).toEqual(me)
  })
  it("requests a fresh login when JWT expires", async () => {
    fetchMock.mockResolvedValueOnce(respond({ auth_enabled: true, methods: ["password"], configured: true }))
      .mockResolvedValueOnce(respond({ detail: "Authentication required" }, 401))
    expect((await resolveSession()).needsLogin).toBe(true)
  })
  it("does not pretend logout succeeded on a network failure", async () => {
    fetchMock.mockRejectedValue(new Error("offline"))
    await assert.rejects(logoutSession, /offline/)
  })
})
