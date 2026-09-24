"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { useQueryClient } from "@tanstack/react-query"
import { ArrowRight, LockKeyhole } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { useForm, useWatch } from "react-hook-form"

import { loginAccount, registerAccount, sessionQueryKey } from "@/entities/session"
import { ApiError } from "@/shared/api/http"
import { Button } from "@/shared/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card"
import { Field, FieldError, FieldLabel } from "@/shared/ui/field"
import { Input } from "@/shared/ui/input"
import { NativeSelect, NativeSelectOption } from "@/shared/ui/native-select"

import { accessSchema, type AccessValues } from "../model/schema"

export function AccessForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter()
  const queryClient = useQueryClient()
  const [serverError, setServerError] = useState("")
  const [busy, setBusy] = useState(false)
  const form = useForm<AccessValues>({
    resolver: zodResolver(accessSchema(mode)),
    defaultValues: { email: "", password: "", full_name: "", role: "operator", invite_code: "" },
  })
  const role = useWatch({ control: form.control, name: "role" })

  async function submit(values: AccessValues) {
    setBusy(true)
    setServerError("")
    try {
      const user = mode === "login"
        ? await loginAccount({ email: values.email, password: values.password })
        : await registerAccount({
            email: values.email,
            full_name: values.full_name ?? "",
            password: values.password,
            role: values.role,
            invite_code: values.invite_code,
          })
      queryClient.clear()
      queryClient.setQueryData(sessionQueryKey, user)
      router.replace("/dashboard")
    } catch (error) {
      setServerError(error instanceof ApiError ? error.detail : "Не удалось выполнить запрос")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="w-full max-w-md border border-border/70 shadow-2xl shadow-black/10">
      <CardHeader className="space-y-2 px-7 pt-7">
        <div className="mb-4 flex size-11 items-center justify-center rounded-xl bg-primary/15 text-primary"><LockKeyhole className="size-5" /></div>
        <CardTitle className="text-2xl font-semibold">{mode === "login" ? "Вход в Vena" : "Создать аккаунт"}</CardTitle>
        <CardDescription>{mode === "login" ? "Войдите в рабочее пространство инфраструктуры" : "Выберите роль и заполните данные для доступа"}</CardDescription>
      </CardHeader>
      <CardContent className="px-7 pb-7">
        <form onSubmit={form.handleSubmit(submit)} className="space-y-4">
          {mode === "register" && (
            <Field>
              <FieldLabel htmlFor="full_name">Имя и фамилия</FieldLabel>
              <Input id="full_name" autoComplete="name" {...form.register("full_name")} />
              <FieldError>{form.formState.errors.full_name?.message}</FieldError>
            </Field>
          )}
          <Field>
            <FieldLabel htmlFor="email">Email</FieldLabel>
            <Input id="email" type="email" autoComplete="email" {...form.register("email")} />
            <FieldError>{form.formState.errors.email?.message}</FieldError>
          </Field>
          <Field>
            <FieldLabel htmlFor="password">Пароль</FieldLabel>
            <Input id="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} {...form.register("password")} />
            <FieldError>{form.formState.errors.password?.message}</FieldError>
          </Field>
          {mode === "register" && (
            <>
              <Field>
                <FieldLabel htmlFor="role">Роль</FieldLabel>
                <NativeSelect id="role" {...form.register("role")}>
                  <NativeSelectOption value="operator">Оператор — загрузка и просмотр данных</NativeSelectOption>
                  <NativeSelectOption value="dispatcher">Диспетчер — решения и работы</NativeSelectOption>
                </NativeSelect>
              </Field>
              {role === "dispatcher" && (
                <Field>
                  <FieldLabel htmlFor="invite_code">Код приглашения</FieldLabel>
                  <Input id="invite_code" autoComplete="off" {...form.register("invite_code")} />
                  <p className="text-xs text-muted-foreground">Код нужен, только если он настроен администратором. Первый аккаунт можно создать без кода.</p>
                </Field>
              )}
            </>
          )}
          {serverError && <p role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{serverError}</p>}
          <Button type="submit" size="lg" className="mt-2 w-full" disabled={busy}>
            {busy ? "Подождите…" : mode === "login" ? "Войти" : "Создать аккаунт"}<ArrowRight className="size-4" />
          </Button>
        </form>
        <p className="mt-6 text-center text-sm text-muted-foreground">
          {mode === "login" ? "Нет аккаунта? " : "Уже есть аккаунт? "}
          <Link className="font-medium text-primary hover:underline" href={mode === "login" ? "/register" : "/login"}>{mode === "login" ? "Зарегистрироваться" : "Войти"}</Link>
        </p>
      </CardContent>
    </Card>
  )
}
