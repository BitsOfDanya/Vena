import type { Metadata } from "next"

import { JournalPage } from "@/views/journal"

export const metadata: Metadata = { title: "Журнал" }

export default function Page() {
  return <JournalPage />
}
