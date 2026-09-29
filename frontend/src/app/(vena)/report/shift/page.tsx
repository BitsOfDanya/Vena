import type { Metadata } from "next"

import { ShiftReportPage } from "@/views/shift-report"

export const metadata: Metadata = { title: "Отчёт смены" }

export default function Page() {
  return <ShiftReportPage />
}
