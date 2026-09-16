import type { Metadata } from "next"
import { Geist } from "next/font/google"

import { AppProviders } from "@/app/providers"

import "./globals.css"

const geist = Geist({
  subsets: ["latin", "cyrillic"],
  variable: "--font-geist",
})

export const metadata: Metadata = {
  title: {
    default: "Vena",
    template: "%s · Vena",
  },
  description: "Full-stack product foundation for Vena.",
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ru" className={geist.variable} suppressHydrationWarning>
      <body>
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  )
}
