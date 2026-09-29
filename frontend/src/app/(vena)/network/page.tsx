import type { Metadata } from "next"

import { NetworkPage } from "@/views/network"

export const metadata: Metadata = { title: "Сеть" }

export default function Page() {
  return <NetworkPage />
}
