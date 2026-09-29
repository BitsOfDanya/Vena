"use client"

import Link from "next/link"
import * as React from "react"

import {
  calibrationLine,
  dailyTopKLines,
  leadTimeLine,
  modelWhatPredicts,
  scenarioTitle,
  topKTrustLine,
  useMlModels,
  verifiedLine,
  type MlModel,
} from "@/entities/analytics"
import { workflowMode } from "@/shared/config/env"
import { Button } from "@/shared/ui/button"
import { LoadingBar, StateMessage } from "@/shared/ui/state-message"

function ModelCard({ model }: { model: MlModel }) {
  const trust = topKTrustLine(model.heldOut?.precisionTop5PerDay, model.horizonHours)
  const topK = dailyTopKLines(model.dailyTopK, model.horizonHours)
  const calib = calibrationLine(model.heldOut?.ece)
  const lead = leadTimeLine(model.leadTime?.medianLeadTimeHours, model.leadTime?.alertPrecisionDedup)
  const verified = verifiedLine(model.heldOut?.period)

  return (
    <article id={model.name} className="scroll-mt-20 border border-border bg-elevated px-4 py-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-[15px] font-semibold">{scenarioTitle(model.scenario)}</h2>
        <span className="font-mono text-[12px] text-faint" title="Технический id модели">
          {model.name}
        </span>
        <span className="text-[12px] text-muted-foreground">
          {model.horizonHours >= 72 ? "3 суток" : model.horizonHours >= 24 ? "сутки" : `${model.horizonHours} ч`}
        </span>
      </div>
      <p className="mt-2 text-[13px] text-muted-foreground">
        <span className="text-faint">Что предсказывает · </span>
        {modelWhatPredicts(model)}
      </p>
      {trust ? (
        <p className="mt-1 text-[13px]">
          <span className="text-faint">Насколько можно верить · </span>
          {trust}
        </p>
      ) : null}
      {topK.slice(1).map((line) => (
        <p key={line} className="mt-0.5 text-[12px] text-muted-foreground">
          {line}
        </p>
      ))}
      {lead ? <p className="mt-1 text-[13px] text-muted-foreground">{lead}</p> : null}
      {calib ? (
        <p className="mt-1 text-[12px] text-muted-foreground" title="ECE / калибровка">
          {calib}
        </p>
      ) : null}
      <p className="mt-1 text-[12px] text-faint">{verified}</p>
      <p className="mt-2 font-mono text-[11px] text-faint">
        обучение {model.trainYears ?? "—"}
        {model.version ? ` · версия ${model.version}` : ""}
        {model.features != null ? ` · ${model.features} признаков` : ""}
      </p>
    </article>
  )
}

export function ModelsPage() {
  const models = useMlModels()

  if (workflowMode !== "api") {
    return (
      <StateMessage
        title="Модели доступны в API-режиме"
        description="Подключите workflowMode=api, чтобы увидеть карточки моделей из /ml/models."
      />
    )
  }

  return (
    <div className="flex size-full min-h-0 flex-col overflow-auto">
      <div className="flex shrink-0 flex-wrap items-center gap-x-6 gap-y-3 px-6 pt-4 pb-3">
        <h1 className="text-[26px] font-semibold tracking-[-0.01em]">Модели</h1>
        <p className="text-[13px] text-muted-foreground">
          Что предсказывает · на какой срок · насколько можно верить · на каких данных проверено
        </p>
        <div className="ml-auto flex items-center gap-3">
          <Button asChild variant="outline" size="sm">
            <Link href="/about">Как работает VENA</Link>
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link href="/effect">К эффекту</Link>
          </Button>
        </div>
      </div>

      <div className="space-y-3 px-6 pb-8">
        {models.isPending ? (
          <LoadingBar className="min-h-40" />
        ) : models.isError ? (
          <StateMessage
            title="Реестр моделей недоступен"
            description="Не удалось загрузить GET /api/v1/ml/models."
            action={
              <Button variant="outline" size="sm" onClick={() => models.refetch()}>
                Повторить
              </Button>
            }
          />
        ) : (models.data ?? []).length === 0 ? (
          <StateMessage title="Нет карточек моделей" description="Файл ml/results/models.json пуст или отсутствует." />
        ) : (
          (models.data ?? []).map((model) => <ModelCard key={model.name} model={model} />)
        )}
      </div>
    </div>
  )
}
