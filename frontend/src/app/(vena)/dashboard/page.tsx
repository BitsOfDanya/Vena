import type { Metadata } from "next"

import { DashboardPage } from "@/views/dashboard"

export const metadata: Metadata = { title: "Дашборд" }

export default function Page() {
  return <DashboardPage />
}
