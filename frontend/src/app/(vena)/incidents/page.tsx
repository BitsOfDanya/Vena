import type { Metadata } from "next"

import { IncidentsPage } from "@/views/incidents"

export const metadata: Metadata = { title: "Инциденты" }

export default function Page() {
  return <IncidentsPage />
}
