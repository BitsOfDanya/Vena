import type { Metadata } from "next"

import { SettingsNotificationsPage } from "@/views/settings"

export const metadata: Metadata = { title: "Notification settings" }

export default function Page() {
  return <SettingsNotificationsPage />
}
