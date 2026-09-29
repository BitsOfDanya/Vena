"use client"

import * as React from "react"
import { toast } from "sonner"

import { DISMISS_REASON_LABEL, useDismissAction, type DismissReason } from "@/entities/maintenance"
import { useWorkspace } from "@/features/workspace"
import { Button } from "@/shared/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/shared/ui/dialog"
import { Field, FieldLabel } from "@/shared/ui/field"
import { NativeSelect, NativeSelectOption } from "@/shared/ui/native-select"
import { Textarea } from "@/shared/ui/textarea"

export function DismissActionDialog({ actionId, trigger }: { actionId: string; trigger: React.ReactElement }) {
  const { now } = useWorkspace()
  const dismiss = useDismissAction(now)
  const [open, setOpen] = React.useState(false)
  const [reason, setReason] = React.useState<DismissReason>("false_alarm")
  const [note, setNote] = React.useState("")

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    await dismiss.mutateAsync({ id: actionId, reason, note: note.trim() })
    toast.success(`Работа ${actionId} отклонена`, { description: DISMISS_REASON_LABEL[reason] })
    setOpen(false)
    setNote("")
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>Отклонить {actionId}</DialogTitle>
            <DialogDescription>
              Решение без выезда бригады. Причина сохраняется в журнале прогнозов и используется для дообучения модели.
            </DialogDescription>
          </DialogHeader>
          <Field>
            <FieldLabel htmlFor={`dismiss-reason-${actionId}`}>Причина</FieldLabel>
            <NativeSelect
              id={`dismiss-reason-${actionId}`}
              className="w-full"
              value={reason}
              onChange={(event) => setReason(event.target.value as DismissReason)}
            >
              {(Object.keys(DISMISS_REASON_LABEL) as DismissReason[]).map((value) => (
                <NativeSelectOption key={value} value={value}>
                  {DISMISS_REASON_LABEL[value]}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </Field>
          <Field>
            <FieldLabel htmlFor={`dismiss-note-${actionId}`}>Примечание (необязательно)</FieldLabel>
            <Textarea
              id={`dismiss-note-${actionId}`}
              rows={3}
              maxLength={500}
              placeholder="Например: подтверждено по камере 12"
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Отмена
            </Button>
            <Button type="submit" disabled={dismiss.isPending}>
              Отклонить
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
