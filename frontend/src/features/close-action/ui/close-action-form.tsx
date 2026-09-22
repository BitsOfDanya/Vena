"use client"

import * as React from "react"
import { toast } from "sonner"

import { OUTCOME_LABEL, useCloseAction, type ActionOutcome } from "@/entities/maintenance"
import { useWorkspace } from "@/features/workspace"
import { Button } from "@/shared/ui/button"
import { Field, FieldLabel } from "@/shared/ui/field"
import { NativeSelect, NativeSelectOption } from "@/shared/ui/native-select"
import { Textarea } from "@/shared/ui/textarea"

export function CloseActionForm({ actionId, onClosed }: { actionId: string; onClosed?: () => void }) {
  const { now } = useWorkspace()
  const close = useCloseAction(now)
  const [outcome, setOutcome] = React.useState<ActionOutcome>("confirmed_issue")
  const [note, setNote] = React.useState("")

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    await close.mutateAsync({ id: actionId, outcome, note })
    toast.success(`Action ${actionId} closed`, { description: OUTCOME_LABEL[outcome] })
    setNote("")
    onClosed?.()
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <Field>
        <FieldLabel htmlFor="close-outcome">Result</FieldLabel>
        <NativeSelect id="close-outcome" className="w-full" value={outcome} onChange={(event) => setOutcome(event.target.value as ActionOutcome)}>
          {(Object.keys(OUTCOME_LABEL) as ActionOutcome[]).map((value) => (
            <NativeSelectOption key={value} value={value}>
              {OUTCOME_LABEL[value]}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </Field>
      <Field>
        <FieldLabel htmlFor="close-note">Note (optional)</FieldLabel>
        <Textarea id="close-note" rows={3} value={note} onChange={(event) => setNote(event.target.value)} />
      </Field>
      <Button type="submit" disabled={close.isPending}>
        Close action
      </Button>
    </form>
  )
}
