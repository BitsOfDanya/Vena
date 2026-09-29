import type { Metadata } from "next"

import { ActionsPage } from "@/views/actions"

export const metadata: Metadata = { title: "Работы" }

export default function Page() {
  return <ActionsPage />
}
