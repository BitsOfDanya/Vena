import type { PredictionScenario } from "./types"

export const SCENARIO_LABEL: Record<PredictionScenario, string> = {
  flooding: "Подтопление",
  fire: "Пожар",
  power_loss: "Потеря питания",
  ventilation: "Отказ вентиляции",
  equipment: "Отказ оборудования",
}
