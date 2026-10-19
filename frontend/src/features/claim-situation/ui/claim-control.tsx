"use client"

import { toast } from "sonner"

import { useClaimSituation, useReleaseSituation } from "@/entities/prediction"
import { useAuthSession } from "@/features/auth"
import { errorMessage } from "@/shared/api/http"

type ClaimTarget = { id: string; claimedBy?: string | null; claimedBySubject?: string | null }

const BUTTON =
  "h-8 cursor-pointer rounded-md border border-border px-3 text-[13px] outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring/60 disabled:cursor-not-allowed disabled:opacity-60"

export function ClaimControl({ situation }: { situation: ClaimTarget }) {
  const { me } = useAuthSession()
  const claim = useClaimSituation()
  const release = useReleaseSituation()
  const busy = claim.isPending || release.isPending
  const holder = { situationId: situation.id, name: me?.subject ?? "", subject: me?.subject ?? "" }

  if (situation.claimedBy) {
    const canRelease = me?.role === "admin" || (me !== null && me.subject === situation.claimedBySubject)
    return (
      <span className="inline-flex items-center gap-2">
        <span className="text-[12.5px] text-muted-foreground">
          Ведёт: <span className="font-medium text-foreground">{situation.claimedBy}</span>
        </span>
        {canRelease ? (
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              release.mutate(holder, {
                onError: (error) =>
                  toast.error("Не удалось отпустить ситуацию", {
                    description: errorMessage(error, "Сервер не принял изменения. Попробуйте ещё раз."),
                  }),
              })
            }
            className={BUTTON}
          >
            Отпустить
          </button>
        ) : null}
      </span>
    )
  }

  if (!me || me.role === "viewer") return null

  return (
    <button
      type="button"
      disabled={busy}
      onClick={() =>
        claim.mutate(holder, {
          onError: (error) =>
            toast.error("Не удалось взять ситуацию в работу", {
              description: errorMessage(error, "Сервер не принял изменения. Попробуйте ещё раз."),
            }),
        })
      }
      className={BUTTON}
    >
      Взять в работу
    </button>
  )
}
