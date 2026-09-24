import { z } from "zod"

import { apiFetch } from "@/shared/api/http"

const importSchema = z.object({
  id: z.string(), kind: z.enum(["events", "channels", "objects", "edges"]), filename: z.string(),
  size_bytes: z.number(), status: z.string(), total_rows: z.number(),
  accepted_rows: z.number(), rejected_rows: z.number(), error: z.string(),
  created_at: z.string(), finished_at: z.string().nullable(),
})

export type ImportBatch = z.infer<typeof importSchema>
export type ImportKind = ImportBatch["kind"]

export async function getImports(): Promise<ImportBatch[]> {
  return z.array(importSchema).parse(await apiFetch<unknown>("/api/v1/imports"))
}

export async function uploadImport(kind: ImportKind, file: File): Promise<ImportBatch> {
  const body = new FormData()
  body.append("file", file)
  return importSchema.parse(
    await apiFetch<unknown>(`/api/v1/imports?kind=${kind}`, { method: "POST", body })
  )
}
