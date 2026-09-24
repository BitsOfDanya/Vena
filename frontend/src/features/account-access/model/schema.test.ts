import { describe, expect, it } from "vitest"

import { accessSchema } from "./schema"

const fields = {
  email: "operator@example.test",
  password: "valid-password",
  full_name: "",
  role: "operator" as const,
  invite_code: "",
}

describe("access form validation", () => {
  it("allows login without registration-only fields", () => {
    expect(accessSchema("login").safeParse({ ...fields, password: "short" }).success).toBe(true)
  })

  it("requires a name and a long password for registration", () => {
    expect(accessSchema("register").safeParse(fields).success).toBe(false)
    expect(accessSchema("register").safeParse({ ...fields, full_name: "Оператор" }).success).toBe(true)
  })
})
