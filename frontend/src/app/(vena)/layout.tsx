import { AppShell } from "@/widgets/app-shell"

export default function VenaLayout({ children }: LayoutProps<"/">) {
  return <AppShell>{children}</AppShell>
}
