import type { Metadata } from "next"

import { EffectPage } from "@/views/effect"

export const metadata: Metadata = { title: "Эффект" }

export default function Page() {
  return <EffectPage />
}
