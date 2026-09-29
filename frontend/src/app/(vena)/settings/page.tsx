import type { Metadata } from "next"

import { SettingsOverviewPage } from "@/views/settings"

export const metadata: Metadata = { title: "Настройки" }

export default function Page() {
  return <SettingsOverviewPage />
}
