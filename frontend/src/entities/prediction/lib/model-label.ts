
const PREFIX: Record<string, string> = {
  phase: "Питание",
  power: "Питание",
  pump: "Подтопление",
  flood: "Подтопление",
  smoke: "Пожар",
  fan: "Вентиляция",
  alarm: "Тревоги",
}

const NAMED: Record<string, string> = {
  object_power_24h: "Питание объекта, сутки",
  object_flood_24h: "Подтопление станции, сутки",
  object_flood_6h: "Подтопление станции, 6 ч",
  object_fire_24h: "Пожар на объекте, сутки",
}

export function modelLabel(modelId: string | null | undefined) {
  if (!modelId) return "—"
  if (NAMED[modelId]) return NAMED[modelId]
  const prefix = modelId.split("_")[0] ?? ""
  const base = PREFIX[prefix]
  const hours = modelId.includes("72") ? "3 суток" : modelId.includes("24") ? "сутки" : null
  if (base && hours) return `${base}, ${hours}`
  if (base) return base
  return modelId
}
