import type { Metadata } from "next"

import { PulsePage } from "@/views/pulse"

export const metadata: Metadata = { title: "Pulse" }

export default function Page() {
  return <PulsePage />
}
