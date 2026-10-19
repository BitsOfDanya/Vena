"use client"

import { useProspective } from "@/entities/analytics"
import { formatProbability, modelLabel } from "@/entities/prediction"
import { formatDateTime } from "@/shared/lib/time"

function share(value: number | null) {
  return value === null ? "—" : formatProbability(value)
}

export function ProspectivePanel() {
  const prospective = useProspective()
  const data = prospective.data
  if (!data || (!Object.keys(data.models).length && !Object.keys(data.objects).length)) return null
  const objects = Object.entries(data.objects)

  return (
    <section aria-label="Проспективная проверка" className="mx-6 mb-6 border border-border bg-elevated">
      <div className="border-b border-border-soft px-5 py-3">
        <h2 className="text-[12px]">Проспективная проверка</h2>
        <p className="mt-1 text-[12px] text-muted-foreground">
          Прогнозы, выданные после {formatDateTime(data.start)}, сверены с событиями, пришедшими позже, по{" "}
          {formatDateTime(data.now)}. Засчитываются прогнозы с истёкшим горизонтом.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-left text-[13px]">
          <thead className="border-b border-border-soft text-[12px] text-faint">
            <tr>
              <th className="px-5 py-2 font-medium">Модель</th>
              <th className="px-5 py-2 text-right font-medium">Прогнозы</th>
              <th className="px-5 py-2 text-right font-medium">Предсказано</th>
              <th className="px-5 py-2 text-right font-medium">Наблюдено</th>
              <th className="px-5 py-2 text-right font-medium">Точность тревог</th>
              <th className="px-5 py-2 text-right font-medium">Эпизоды с предупреждением</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(data.models).map(([name, model]) => (
              <tr key={name} className="border-b border-border-soft last:border-b-0">
                <td className="px-5 py-2 text-[13px]" title={name}>
                  {modelLabel(name)}
                </td>
                <td className="px-5 py-2 text-right font-mono tabular-nums">{model.forecasts}</td>
                <td className="px-5 py-2 text-right font-mono tabular-nums">{formatProbability(model.meanProbability)}</td>
                <td className="px-5 py-2 text-right font-mono tabular-nums">{formatProbability(model.eventRate)}</td>
                <td className="px-5 py-2 text-right font-mono tabular-nums">
                  {share(model.alertPrecision)}
                  <span className="ml-1 text-[11px] text-faint">из {model.alerts}</span>
                </td>
                <td className="px-5 py-2 text-right font-mono tabular-nums">
                  {share(model.episodeRecall)}
                  <span className="ml-1 text-[11px] text-faint">из {model.episodes}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {objects.length ? (
        <div className="overflow-x-auto border-t border-border-soft">
          <table className="w-full min-w-[760px] text-left text-[13px]">
            <thead className="border-b border-border-soft text-[12px] text-faint">
              <tr>
                <th className="px-5 py-2 font-medium">Модель объекта</th>
                <th className="px-5 py-2 text-right font-medium">Списков</th>
                <th className="px-5 py-2 text-right font-medium">Предсказано</th>
                <th className="px-5 py-2 text-right font-medium">Наблюдено</th>
                <th className="px-5 py-2 text-right font-medium">Точность топ-3</th>
                <th className="px-5 py-2 text-right font-medium">Инциденты с объектом в топ-3</th>
              </tr>
            </thead>
            <tbody>
              {objects.map(([name, model]) => (
                <tr key={name} className="border-b border-border-soft last:border-b-0">
                  <td className="px-5 py-2 text-[13px]" title={name}>
                    {modelLabel(name)}
                  </td>
                  <td className="px-5 py-2 text-right font-mono tabular-nums">{model.lists}</td>
                  <td className="px-5 py-2 text-right font-mono tabular-nums">{formatProbability(model.meanProbability)}</td>
                  <td className="px-5 py-2 text-right font-mono tabular-nums">{formatProbability(model.eventRate)}</td>
                  <td className="px-5 py-2 text-right font-mono tabular-nums">{share(model.top3Precision)}</td>
                  <td className="px-5 py-2 text-right font-mono tabular-nums">
                    {share(model.incidentRecallTop3)}
                    <span className="ml-1 text-[11px] text-faint">из {model.incidents}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <p className="px-5 py-3 text-[11px] leading-relaxed text-faint">
        Предсказано — средняя вероятность прогнозов, Наблюдено — доля, после которой событие действительно началось; близость
        значений показывает калибровку. Точность тревог — доля тревог уровней critical и high с событием в горизонте. Модели
        объекта сверяются с инцидентами реестра: утренний список на сутки и список подтопления на 6 ч, засчитывается объект в топ-3
        списка, выданного до начала инцидента.
      </p>
    </section>
  )
}
