"use client"

import { useMutation, useQueryClient } from "@tanstack/react-query"
import { FileCheck2, FileUp, Info } from "lucide-react"
import { useState } from "react"

import { uploadImport, useImports, type ImportKind } from "@/entities/import-batch"
import { useSession } from "@/entities/session"
import { ApiError } from "@/shared/api/http"
import { Badge } from "@/shared/ui/badge"
import { Button } from "@/shared/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card"
import { Input } from "@/shared/ui/input"
import { NativeSelect, NativeSelectOption } from "@/shared/ui/native-select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/shared/ui/table"

const kinds: Record<ImportKind, string> = { events: "Журнал датчиков", channels: "Реестр каналов", objects: "Дерево объектов", edges: "Связи сети" }

export function ImportsPage() {
  const user = useSession()
  const imports = useImports()
  const queryClient = useQueryClient()
  const [kind, setKind] = useState<ImportKind>("events")
  const [file, setFile] = useState<File | null>(null)
  const upload = useMutation({
    mutationFn: () => {
      if (!file) throw new Error("Выберите файл")
      return uploadImport(kind, file)
    },
    onSuccess: () => {
      setFile(null)
      void queryClient.invalidateQueries({ queryKey: ["imports"] })
      void queryClient.invalidateQueries({ queryKey: ["data"] })
      void queryClient.invalidateQueries({ queryKey: ["map"] })
    },
  })

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-5 md:p-8">
      <div className="mx-auto max-w-[1300px] space-y-6">
        <div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">Источники данных</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">Загрузка данных</h1><p className="mt-1 text-sm text-muted-foreground">Добавляйте журналы и справочники. Статус каждой загрузки сохраняется в системе.</p></div>
        {user.data?.role === "operator" ? (
          <Card className="border border-border/70"><CardHeader><CardTitle className="flex items-center gap-2"><FileUp className="size-5 text-primary" />Новый импорт</CardTitle><CardDescription>CSV или XLSX до 25 МБ. Загружайте обезличенные данные.</CardDescription></CardHeader><CardContent className="space-y-5">
            <div className="grid gap-4 md:grid-cols-[240px_1fr_auto] md:items-end">
              <div className="space-y-2"><label htmlFor="kind" className="text-sm font-medium">Тип данных</label><NativeSelect id="kind" value={kind} onChange={(event) => setKind(event.target.value as ImportKind)}><NativeSelectOption value="events">Журнал датчиков</NativeSelectOption><NativeSelectOption value="channels">Реестр каналов</NativeSelectOption><NativeSelectOption value="objects">Дерево объектов</NativeSelectOption><NativeSelectOption value="edges">Связи сети</NativeSelectOption></NativeSelect></div>
              <div className="space-y-2"><label htmlFor="import-file" className="text-sm font-medium">Файл</label><Input key={file ? file.name : "empty"} id="import-file" type="file" accept=".csv,.xlsx" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></div>
              <Button size="lg" disabled={!file || upload.isPending} onClick={() => upload.mutate()}>{upload.isPending ? "Загрузка…" : "Загрузить"}</Button>
            </div>
            {upload.isError && <p role="alert" className="text-sm text-destructive">{upload.error instanceof ApiError ? upload.error.detail : upload.error.message}</p>}
            {upload.isSuccess && <p role="status" className="flex items-center gap-2 text-sm text-chart-2"><FileCheck2 className="size-4" />Файл принят. Обработка запущена.</p>}
            <p className="flex items-start gap-2 rounded-lg bg-secondary/60 p-3 text-xs leading-5 text-muted-foreground"><Info className="mt-0.5 size-4 shrink-0" />Для журнала нужны ID записи, ID канала, значение и дата. Для каналов — ID и тег объекта. Для дерева — ID, название, а для карты ещё широта и долгота. Для связей сети — ID двух существующих объектов.</p>
          </CardContent></Card>
        ) : <Card className="border border-border/70"><CardContent className="flex items-center gap-3 text-sm text-muted-foreground"><Info className="size-5 text-primary" />Загружать данные может оператор. История импортов доступна обеим ролям.</CardContent></Card>}
        <Card className="border border-border/70"><CardHeader><CardTitle>История импортов</CardTitle><CardDescription>Обработка выполняется в отдельном процессе; список обновляется автоматически.</CardDescription></CardHeader><CardContent>
          {imports.data?.length ? <Table><TableHeader><TableRow><TableHead>Файл</TableHead><TableHead>Тип</TableHead><TableHead>Дата</TableHead><TableHead>Статус</TableHead><TableHead>Принято</TableHead><TableHead>Отклонено</TableHead></TableRow></TableHeader><TableBody>{imports.data.map((item) => <TableRow key={item.id}><TableCell className="max-w-64 truncate font-medium" title={item.filename}>{item.filename}</TableCell><TableCell>{kinds[item.kind]}</TableCell><TableCell>{new Date(item.created_at).toLocaleString("ru-RU")}</TableCell><TableCell><Badge variant={item.status === "failed" ? "destructive" : "secondary"}>{item.status === "completed" ? "Готово" : item.status === "completed_with_errors" ? "С ошибками" : item.status === "processing" ? "Обработка" : item.status === "pending" ? "В очереди" : "Ошибка"}</Badge></TableCell><TableCell>{item.accepted_rows}</TableCell><TableCell title={item.error}>{item.rejected_rows}</TableCell></TableRow>)}</TableBody></Table> : <p className="py-10 text-center text-sm text-muted-foreground">Загрузок пока нет</p>}
        </CardContent></Card>
      </div>
    </div>
  )
}
