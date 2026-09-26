"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { useRouter } from "next/navigation"
import * as React from "react"
import { Controller, useForm } from "react-hook-form"
import { toast } from "sonner"

import { STATUS_LABEL, useAssets } from "@/entities/infrastructure"
import {
  ASSIGNEES,
  KIND_LABEL,
  PRIORITY_LABEL,
  useCreateAction,
  type ActionKind,
  type ActionPriority,
} from "@/entities/maintenance"
import { useWorkspace } from "@/features/workspace"
import { HOUR, formatDateTime, fromDateTimeLocal, toDateTimeLocal } from "@/shared/lib/time"
import { Button } from "@/shared/ui/button"
import { Field, FieldError, FieldGroup, FieldLabel } from "@/shared/ui/field"
import { Input } from "@/shared/ui/input"
import { NativeSelect, NativeSelectOption } from "@/shared/ui/native-select"
import { Segmented } from "@/shared/ui/segmented"
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/shared/ui/sheet"
import { Textarea } from "@/shared/ui/textarea"

import { createActionSchema, type CreateActionValues } from "../model/schema"

export type ActionDraft = {
  assetId?: string
  reason?: string
  priority?: ActionPriority
  kind?: ActionKind
  hours?: number
  sourcePredictionId?: string
  sourceModelId?: string
  sourceScore?: number
  sourceHorizonHours?: number
}

const PRIORITY_HOURS: Record<ActionPriority, number> = { high: 24, medium: 48, low: 72 }

export function CreateActionSheet({
  open,
  onOpenChange,
  draft,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  draft: ActionDraft
}) {
  const router = useRouter()
  const { now, horizon } = useWorkspace()
  const assets = useAssets(now, horizon)
  const create = useCreateAction(now)
  const [notify, setNotify] = React.useState(false)
  const priority = draft.priority ?? "medium"

  const defaults = React.useMemo<CreateActionValues>(
    () => ({
      assetId: draft.assetId ?? "",
      reason: draft.reason ?? "",
      kind: draft.kind ?? "inspect",
      priority,
      recommendedAt: toDateTimeLocal(now + (draft.hours ?? PRIORITY_HOURS[priority]) * HOUR),
      assignee: ASSIGNEES[0],
      note: "",
    }),
    [draft, now, priority]
  )

  const {
    control,
    formState: { errors },
    handleSubmit,
    register,
    reset,
  } = useForm<CreateActionValues>({ resolver: zodResolver(createActionSchema), defaultValues: defaults })

  React.useEffect(() => {
    if (open) reset(defaults)
  }, [open, defaults, reset])

  const submit = handleSubmit(async (values) => {
    const fromPrediction = Boolean(draft.sourcePredictionId)
    const action = await create.mutateAsync({
      assetId: values.assetId,
      reason: values.reason,
      kind: values.kind,
      priority: values.priority,
      recommendedAt: fromDateTimeLocal(values.recommendedAt),
      assignee: values.assignee,
      note: values.note,
      source: fromPrediction ? "vena_forecast" : "manual",
      sourceDetail: fromPrediction ? (draft.sourceModelId ?? "ML forecast") : "Диспетчер",
      notifyChannels: notify ? ["in_app", "email"] : ["in_app"],
      sourcePredictionId: draft.sourcePredictionId,
      sourceModelId: draft.sourceModelId,
      sourceScore: draft.sourceScore,
      sourceHorizonHours: draft.sourceHorizonHours,
    })
    onOpenChange(false)
    toast.success(`Action ${action.id} created`, {
      description: `${action.assetId} · ${KIND_LABEL[action.kind]} до ${formatDateTime(action.recommendedAt)}`,
      action: { label: "Open Actions", onClick: () => router.push("/actions") },
    })
  })

  const sorted = [...(assets.data ?? [])].sort((left, right) => right.riskScore - left.riskScore)

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full gap-0 sm:max-w-md">
        <SheetHeader className="border-b">
          <SheetTitle className="text-sm font-medium tracking-[0.12em] uppercase">Create action</SheetTitle>
          <SheetDescription>Запланируйте работу по объекту. Она появится в плане обслуживания.</SheetDescription>
        </SheetHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
            <FieldGroup>
              <Field data-invalid={Boolean(errors.assetId)}>
                <FieldLabel htmlFor="action-asset">Asset</FieldLabel>
                <NativeSelect id="action-asset" className="w-full" aria-invalid={Boolean(errors.assetId)} {...register("assetId")}>
                  <NativeSelectOption value="">Выберите объект</NativeSelectOption>
                  {sorted.map((asset) => (
                    <NativeSelectOption key={asset.id} value={asset.id}>
                      {asset.id} · {STATUS_LABEL[asset.status]} · {Math.round(asset.riskScore)}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
                <FieldError errors={[errors.assetId]} />
              </Field>
              <Field data-invalid={Boolean(errors.reason)}>
                <FieldLabel htmlFor="action-reason">Reason</FieldLabel>
                <Textarea id="action-reason" rows={3} aria-invalid={Boolean(errors.reason)} {...register("reason")} />
                <FieldError errors={[errors.reason]} />
              </Field>
              <Field>
                <FieldLabel htmlFor="action-kind">Action type</FieldLabel>
                <NativeSelect id="action-kind" className="w-full" {...register("kind")}>
                  {(Object.keys(KIND_LABEL) as ActionKind[]).map((kind) => (
                    <NativeSelectOption key={kind} value={kind}>
                      {KIND_LABEL[kind]}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              </Field>
              <Field>
                <FieldLabel>Priority</FieldLabel>
                <Controller
                  control={control}
                  name="priority"
                  render={({ field }) => (
                    <Segmented<ActionPriority>
                      label="Priority"
                      value={field.value}
                      onChange={field.onChange}
                      options={(Object.keys(PRIORITY_LABEL) as ActionPriority[]).map((value) => ({ value, label: PRIORITY_LABEL[value] }))}
                    />
                  )}
                />
              </Field>
              <Field data-invalid={Boolean(errors.recommendedAt)}>
                <FieldLabel htmlFor="action-date">Recommended date (MSK)</FieldLabel>
                <Input id="action-date" type="datetime-local" className="font-mono" {...register("recommendedAt")} />
                <FieldError errors={[errors.recommendedAt]} />
              </Field>
              <Field>
                <FieldLabel htmlFor="action-assignee">Assignee</FieldLabel>
                <NativeSelect id="action-assignee" className="w-full" {...register("assignee")}>
                  {ASSIGNEES.map((name) => (
                    <NativeSelectOption key={name} value={name}>
                      {name}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              </Field>
              <Field>
                <FieldLabel htmlFor="action-note">Note</FieldLabel>
                <Textarea id="action-note" rows={3} {...register("note")} />
              </Field>
              <Field>
                <label className="flex items-start gap-2.5 text-[13px]">
                  <input
                    type="checkbox"
                    checked={notify}
                    onChange={(event) => setNotify(event.target.checked)}
                    className="mt-0.5 size-4 accent-[var(--vena)]"
                  />
                  <span>
                    Notify assignee by email
                    <span className="mt-0.5 block text-[12px] text-muted-foreground">
                      Канал записывается в работу. Отправка появится после подключения почтового шлюза.
                    </span>
                  </span>
                </label>
              </Field>
            </FieldGroup>
          </div>
          <SheetFooter className="flex-row justify-end gap-2 border-t">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              Create action
            </Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  )
}
