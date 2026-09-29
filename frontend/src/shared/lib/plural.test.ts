import { describe, expect, it } from "vitest"

import { formatCount, plural } from "./plural"

const CHANNEL: [string, string, string] = ["канал", "канала", "каналов"]

describe("plural", () => {
  it("picks the Russian form", () => {
    expect(plural(1, CHANNEL)).toBe("канал")
    expect(plural(3, CHANNEL)).toBe("канала")
    expect(plural(11, CHANNEL)).toBe("каналов")
    expect(plural(21, CHANNEL)).toBe("канал")
    expect(plural(95, CHANNEL)).toBe("каналов")
  })

  it("groups thousands", () => {
    expect(formatCount(10765).replace(/\s/g, " ")).toBe("10 765")
  })
})
