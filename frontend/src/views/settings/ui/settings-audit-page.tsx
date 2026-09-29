"use client"

import { useQuery } from "@tanstack/react-query"

import { listAuditLog } from "@/entities/system"
import { Button } from "@/shared/ui/button"
import { StateMessage } from "@/shared/ui/state-message"

import { SettingsSection, SettingsShell } from "./settings-shell"

export function SettingsAuditPage() {
  const audit = useQuery({
    queryKey: ["system", "audit"],
    queryFn: () => listAuditLog(120),
    retry: false,
    staleTime: 10_000,
  })

  return (
    <SettingsShell title="Audit" descriptor="RBAC journal">
      <SettingsSection
        title="Recent entries"
        description="Требуется роль admin при включённой аутентификации. Записи появляются при мутациях actions / settings / spatial / SMVU."
      >
        {audit.isPending ? (
          <p className="text-sm text-muted-foreground">Загрузка журнала…</p>
        ) : audit.isError ? (
          <StateMessage
            title="Журнал недоступен"
            description="Нужна учётная запись администратора, либо сервис временно недоступен."
            action={
              <Button variant="outline" size="sm" onClick={() => audit.refetch()}>
                Retry
              </Button>
            }
          />
        ) : (audit.data?.length ?? 0) === 0 ? (
          <p className="border border-border bg-elevated px-5 py-4 text-sm text-muted-foreground">Записей пока нет.</p>
        ) : (
          <div className="overflow-x-auto border border-border bg-elevated">
            <table className="w-full min-w-[640px] text-left text-[13px]">
              <thead className="border-b border-border text-[11px] tracking-[0.08em] text-faint uppercase">
                <tr>
                  <th className="px-4 py-2 font-medium">Time</th>
                  <th className="px-4 py-2 font-medium">Actor</th>
                  <th className="px-4 py-2 font-medium">Action</th>
                  <th className="px-4 py-2 font-medium">Resource</th>
                </tr>
              </thead>
              <tbody>
                {audit.data?.map((entry) => (
                  <tr key={entry.id} className="border-b border-border-soft last:border-b-0">
                    <td className="px-4 py-2 font-mono text-[12px] tabular-nums whitespace-nowrap">
                      {new Date(entry.at).toLocaleString("ru-RU")}
                    </td>
                    <td className="px-4 py-2">
                      <span className="font-mono text-[12px]">{entry.actor}</span>
                      <span className="ml-2 text-[11px] text-faint">{entry.role}</span>
                    </td>
                    <td className="px-4 py-2 font-mono text-[12px]">{entry.action}</td>
                    <td className="px-4 py-2 font-mono text-[12px] text-muted-foreground">
                      {entry.resource_type}
                      {entry.resource_id ? `:${entry.resource_id}` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SettingsSection>
    </SettingsShell>
  )
}
