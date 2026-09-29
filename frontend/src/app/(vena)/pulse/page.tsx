import type { Metadata } from "next"

import { PulsePage } from "@/views/pulse"

export const metadata: Metadata = { title: "Пульс" }

export default function Page() {
  return <PulsePage />
}
