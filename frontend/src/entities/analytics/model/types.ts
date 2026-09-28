/** Monthly onsets per 100 channels for one scenario; index 0 is January. */
export type SeasonalityRow = { scenario: string; months: number[] }

export type Seasonality = { rows: SeasonalityRow[]; weather: Record<string, number> }

export const SEASONALITY_LABEL: Record<string, string> = {
  flooding: "Затопление камер",
  pump_fault: "Отказ насоса",
  ventilation_fault: "Отказ вентилятора",
  smoke_sensor_fault: "Неисправность датчика дыма",
  smoke_detected: "Обнаружение дыма",
  power_loss: "Потеря питания",
}
