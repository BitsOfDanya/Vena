import type { Metadata } from "next"

import { TimelinePage } from "@/views/timeline"

export const metadata: Metadata = { title: "Таймлайн" }

export default function Page() {
  return <TimelinePage />
}
