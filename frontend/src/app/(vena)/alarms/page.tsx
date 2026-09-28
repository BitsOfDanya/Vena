import type { Metadata } from "next"

import { AlarmsPage } from "@/views/alarms"

export const metadata: Metadata = { title: "Alarms" }

export default function Page() {
  return <AlarmsPage />
}
