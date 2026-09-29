import type { Metadata } from "next"

import { AboutPage } from "@/views/about"

export const metadata: Metadata = { title: "Как работает VENA" }

export default function Page() {
  return <AboutPage />
}
