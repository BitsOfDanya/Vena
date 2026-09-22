import type { Metadata } from "next"

import { NetworkPage } from "@/views/network"

export const metadata: Metadata = { title: "Network" }

export default function Page() {
  return <NetworkPage />
}
