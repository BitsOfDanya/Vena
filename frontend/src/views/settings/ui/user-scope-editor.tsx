"use client"
import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { apiFetch } from "@/shared/api/http"
import { formatCount, plural } from "@/shared/lib/plural"
import { Button } from "@/shared/ui/button"
import { Checkbox } from "@/shared/ui/checkbox"
import { SettingsSection } from "./settings-shell"

type Leaf = { id: string; name: string; channels: number }
type ObjectTree = {
  available: boolean
  districts: { id: string; name: string; channels: number; complexes: (Leaf & { objects: Leaf[] })[] }[]
  unassigned: Leaf[]
}

function Option({ value, label, hint, selected, disabled, onToggle }: {
  value: string; label: string; hint?: string; selected: Set<string>; disabled: boolean; onToggle: (value: string) => void
}) {
  return <label className="flex items-center gap-2 py-0.5 text-sm">
    <Checkbox checked={selected.has(value)} disabled={disabled} onCheckedChange={() => onToggle(value)} />
    <span className="truncate">{label}</span>{hint ? <span className="text-xs text-muted-foreground">{hint}</span> : null}
  </label>
}

export function UserScopeEditor({ username, scopes, busy, onSave, onCancel }: {
  username: string; scopes: string[]; busy: boolean; onSave: (scopes: string[]) => void; onCancel: () => void
}) {
  const tree = useQuery({ queryKey: ["objects-tree"], queryFn: () => apiFetch<ObjectTree>("/api/v1/objects/tree") })
  const [all, setAll] = React.useState(scopes.includes("all"))
  const [selected, setSelected] = React.useState(() => new Set(scopes.filter(scope => scope !== "all")))
  const toggle = (value: string) => setSelected(current => {
    const next = new Set(current)
    if (next.has(value)) next.delete(value)
    else next.add(value)
    return next
  })
  const option = (value: string, label: string, channels?: number) =>
    <Option key={value} value={value} label={label} selected={selected} disabled={all || busy} onToggle={toggle}
      hint={channels === undefined ? undefined : `${formatCount(channels)} ${plural(channels, ["канал", "канала", "каналов"])}`} />
  return <SettingsSection title={`Область видимости: ${username}`} description="Права суммируются: пользователь видит объекты всех отмеченных районов, комплексов и объектов.">
    <div className="space-y-3 border border-border p-4">
      <label className="flex items-center gap-2 text-sm font-medium"><Checkbox checked={all} disabled={busy} onCheckedChange={value => setAll(value === true)} />Все объекты</label>
      {tree.isError && <p role="alert" className="text-sm text-status-critical">Не удалось получить справочник объектов.</p>}
      {tree.data && !tree.data.available && <p className="text-xs text-muted-foreground">Справочник объектов не загружен: доступен выбор отдельных объектов.</p>}
      {tree.data && <div className="max-h-80 space-y-2 overflow-y-auto border border-border-soft p-2">
        {tree.data.districts.map(district => <div key={district.id || "none"}>
          {district.id ? option(`district:${district.id}`, district.name, district.channels) : null}
          {district.complexes.map(item => <div key={item.id} className="ml-4">
            {option(`complex:${item.id}`, item.name, item.channels)}
            <div className="ml-6 grid gap-x-4 sm:grid-cols-2">{item.objects.map(leaf => option(`object:${leaf.id}`, leaf.name))}</div>
          </div>)}
        </div>)}
        {tree.data.unassigned.length > 0 && <div className="grid gap-x-4 sm:grid-cols-2">{tree.data.unassigned.map(leaf => option(`object:${leaf.id}`, leaf.name))}</div>}
      </div>}
      <div className="flex gap-3">
        <Button disabled={busy || (!all && selected.size === 0)} onClick={() => onSave(all ? ["all"] : [...selected])}>Сохранить область</Button>
        <Button variant="outline" onClick={onCancel}>Отмена</Button>
      </div>
    </div>
  </SettingsSection>
}
