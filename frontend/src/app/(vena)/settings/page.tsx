import type { Metadata } from "next"

import { SettingsOverviewPage } from "@/views/settings"

export const metadata: Metadata = { title: "Settings" }

export default function Page() {
  return <SettingsOverviewPage />
}
