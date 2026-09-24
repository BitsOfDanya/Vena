import { WorkspaceLayout } from "./workspace-layout"

export default function VenaLayout({ children }: LayoutProps<"/">) {
  return <WorkspaceLayout>{children}</WorkspaceLayout>
}
