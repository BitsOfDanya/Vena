import type { Metadata } from "next"
import localFont from "next/font/local"

import { AppProviders } from "@/app/providers"

import "./globals.css"

const sans = localFont({
  src: "./fonts/plex-sans.woff2",
  weight: "100 700",
  variable: "--font-plex-sans",
  display: "swap",
})

const mono = localFont({
  src: [
    { path: "./fonts/plex-mono-400.woff2", weight: "400" },
    { path: "./fonts/plex-mono-500.woff2", weight: "500" },
  ],
  variable: "--font-plex-mono",
  display: "swap",
})

export const metadata: Metadata = {
  title: {
    default: "VENA",
    template: "%s · VENA",
  },
  description: "Прогноз инцидентов и работы по инженерным коллекторам.",
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ru" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <body>
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  )
}
