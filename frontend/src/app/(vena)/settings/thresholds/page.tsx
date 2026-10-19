import type { Metadata } from "next"

import { SettingsThresholdsPage } from "@/views/settings"

export const metadata: Metadata = { title: "Пороги и горизонты" }

export default function Page() {
  return <SettingsThresholdsPage />
}
