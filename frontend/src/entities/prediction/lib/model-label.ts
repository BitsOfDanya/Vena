/** Human labels for model ids on dispatcher-facing screens. */

const PREFIX: Record<string, string> = {
  phase: "Питание",
  power: "Питание",
  pump: "Подтопление",
  flood: "Подтопление",
  smoke: "Пожар",
  fan: "Вентиляция",
  alarm: "Тревоги",
}

export function modelLabel(modelId: string | null | undefined) {
  if (!modelId) return "—"
  const prefix = modelId.split("_")[0] ?? ""
  const base = PREFIX[prefix]
  const hours = modelId.includes("72") ? "3 суток" : modelId.includes("24") ? "сутки" : null
  if (base && hours) return `${base}, ${hours}`
  if (base) return base
  return modelId
}

export function modelLabelWithId(modelId: string | null | undefined) {
  if (!modelId) return "—"
  const human = modelLabel(modelId)
  return human === modelId ? modelId : `${human}`
}
