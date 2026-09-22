import type { Metadata } from "next"

import { SettingsIntegrationsPage } from "@/views/settings"

export const metadata: Metadata = { title: "Integrations" }

export default function Page() {
  return <SettingsIntegrationsPage />
}
