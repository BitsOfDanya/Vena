import type { Metadata } from "next"

import { DesignSystemPage } from "@/views/design-system"

export const metadata: Metadata = {
  title: "Дизайн-система",
  description: "Компоненты, токены и состояния интерфейса Vena.",
}

export default function Page() {
  return <DesignSystemPage />
}
