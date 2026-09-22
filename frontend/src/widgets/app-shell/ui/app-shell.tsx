"use client"

import * as React from "react"

import { WorkspaceProvider } from "@/features/workspace"
import { CommandPalette } from "@/widgets/command-palette"

import { SystemNoticeBar } from "@/widgets/system-notice"

import { AppHeader } from "./app-header"

export function AppShell({ children }: { children: React.ReactNode }) {
  const [searchOpen, setSearchOpen] = React.useState(false)

  return (
    <WorkspaceProvider>
      <div className="flex h-svh min-h-0 w-full flex-col overflow-hidden bg-background">
        <AppHeader onOpenSearch={() => setSearchOpen(true)} />
        <SystemNoticeBar />
        <main className="relative flex min-h-0 flex-1 flex-col overflow-hidden">{children}</main>
      </div>
      <CommandPalette open={searchOpen} onOpenChange={setSearchOpen} />
    </WorkspaceProvider>
  )
}
