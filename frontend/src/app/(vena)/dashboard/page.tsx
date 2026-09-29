import type { Metadata } from "next"

import { DashboardPage } from "@/views/dashboard"

export const metadata: Metadata = { title: "Сводка" }

export default function Page() {
  return <DashboardPage />
}
