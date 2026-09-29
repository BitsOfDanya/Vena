import type { Metadata } from "next"

import { AlarmsPage } from "@/views/alarms"

export const metadata: Metadata = { title: "Алармы" }

export default function Page() {
  return <AlarmsPage />
}
