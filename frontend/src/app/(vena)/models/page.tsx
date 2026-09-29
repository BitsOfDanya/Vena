import type { Metadata } from "next"

import { ModelsPage } from "@/views/models"

export const metadata: Metadata = { title: "Модели" }

export default function Page() {
  return <ModelsPage />
}
