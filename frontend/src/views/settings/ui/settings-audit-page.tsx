"use client"

import { useQuery } from "@tanstack/react-query"

import { listAuditLog } from "@/entities/system"
import { Button } from "@/shared/ui/button"
import { StateMessage } from "@/shared/ui/state-message"

import { SettingsSection, SettingsShell } from "./settings-shell"

const roles: Record<string, string> = { admin: "Администратор", dispatcher: "Диспетчер", viewer: "Наблюдатель" }
const actions: Record<string, string> = {
  "user.create": "Создание пользователя", "user.update": "Изменение доступа", "user.password_reset": "Сброс пароля",
  "auth.ldap_login": "Вход через LDAP / AD", "import.validate": "Проверка файла", "import.apply": "Применение загрузки",
  "equipment.update": "Обновление реестра", "equipment.sync": "Синхронизация реестра", "stand.cleanup": "Очистка стенда",
  "action.create": "Создание работы", "action.patch": "Изменение работы", "action.approve": "Согласование работы",
  "action.dismissed": "Отклонение рекомендации", "action.assign": "Назначение исполнителя", "action.result": "Результат работы",
  "action.planned": "Работа запланирована", "action.in_progress": "Работа начата", "action.completed": "Работа завершена", "action.cancelled": "Работа отменена",
  "notification.create": "Создание уведомления", "notification.patch": "Изменение уведомления",
  "settings.notifications.update": "Настройка уведомлений", "predictions.refresh": "Обновление прогнозов", "smvu.ingest": "Приём событий",
  "spatial.import_geojson": "Загрузка карты GeoJSON", "spatial.import_wkt": "Загрузка карты WKT", "spatial.reset_demo": "Сброс демонстрационной карты",
}
const resources: Record<string, string> = { user: "Пользователь", action: "Работа", notification: "Уведомление", equipment: "Оборудование", integration_run: "Загрузка", database: "База данных", settings: "Настройки", snapshot: "Снимок прогнозов", smvu_batch: "Пакет событий", spatial_layer: "Карта" }

export function SettingsAuditPage() {
  const audit = useQuery({
    queryKey: ["system", "audit"],
    queryFn: () => listAuditLog(120),
    retry: false,
    staleTime: 10_000,
  })

  return (
    <SettingsShell title="Аудит" descriptor="Контроль доступа">
      <SettingsSection
        title="Последние записи"
        description="Раздел администратора. Здесь сохраняются изменения работ, настроек, пользователей, загрузки данных и события интеграций."
      >
        {audit.isPending ? (
          <p className="text-sm text-muted-foreground">Загрузка журнала…</p>
        ) : audit.isError ? (
          <StateMessage
            title="Журнал недоступен"
            description="Нужна учётная запись администратора, либо сервис временно недоступен."
            action={
              <Button variant="outline" size="sm" onClick={() => audit.refetch()}>
                Повторить
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
                  <th className="px-4 py-2 font-medium">Время</th>
                  <th className="px-4 py-2 font-medium">Исполнитель</th>
                  <th className="px-4 py-2 font-medium">Действие</th>
                  <th className="px-4 py-2 font-medium">Ресурс</th>
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
                      <span className="ml-2 text-[11px] text-faint">{roles[entry.role] ?? entry.role}</span>
                    </td>
                    <td className="px-4 py-2 font-mono text-[12px]">{actions[entry.action] ?? entry.action}</td>
                    <td className="px-4 py-2 font-mono text-[12px] text-muted-foreground">
                      {resources[entry.resource_type] ?? entry.resource_type}
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
