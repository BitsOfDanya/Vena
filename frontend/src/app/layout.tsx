import type { Metadata } from "next"
import localFont from "next/font/local"

import { AppProviders } from "@/app/providers"

import "./globals.css"

const geist = localFont({
  src: "./fonts/geist-latin.woff2",
  variable: "--font-geist",
  display: "swap",
})

const geistMono = localFont({
  src: "./fonts/geist-mono-latin.woff2",
  variable: "--font-geist-mono",
  display: "swap",
})

export const metadata: Metadata = {
  title: {
    default: "Vena",
    template: "%s · Vena",
  },
  description: "Прогноз инцидентов и работы по инженерным коллекторам.",
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ru" className={`${geist.variable} ${geistMono.variable}`} suppressHydrationWarning>
      <body>
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  )
}
