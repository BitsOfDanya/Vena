import type { Metadata } from "next"

import { AboutPage } from "@/views/about"

export const metadata: Metadata = { title: "О сервисе" }

export default function Page() {
  return <AboutPage />
}
