import type { Metadata } from "next"

import { SettingsNotificationsPage } from "@/views/settings"

export const metadata: Metadata = { title: "Уведомления" }

export default function Page() {
  return <SettingsNotificationsPage />
}
