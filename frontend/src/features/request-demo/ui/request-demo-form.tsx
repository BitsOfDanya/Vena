"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { ArrowRight, Send } from "lucide-react"
import { useForm } from "react-hook-form"
import { toast } from "sonner"

import {
  requestDemoSchema,
  type RequestDemoValues,
} from "@/features/request-demo/model/schema"
import { Button } from "@/shared/ui/button"
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/shared/ui/field"
import { Input } from "@/shared/ui/input"
import { Textarea } from "@/shared/ui/textarea"

export function RequestDemoForm() {
  const {
    formState: { errors, isSubmitting },
    handleSubmit,
    register,
    reset,
  } = useForm<RequestDemoValues>({
    resolver: zodResolver(requestDemoSchema),
    defaultValues: { name: "", email: "", context: "" },
  })

  const onSubmit = handleSubmit(async (values) => {
    await new Promise((resolve) => setTimeout(resolve, 350))
    toast.success(`Спасибо, ${values.name}`, {
      description: "Форма и Zod-валидация работают. API-мутацию подключим к продуктовой задаче.",
    })
    reset()
  })

  return (
    <form className="rounded-2xl border bg-card/90 p-5 shadow-sm backdrop-blur" onSubmit={onSubmit}>
      <FieldGroup>
        <div>
          <p className="font-heading text-lg font-semibold">Проверить форму</p>
          <p className="mt-1 text-sm text-muted-foreground">
            React Hook Form и Zod уже связаны в готовом примере.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field data-invalid={Boolean(errors.name)}>
            <FieldLabel htmlFor="name">Имя</FieldLabel>
            <Input
              id="name"
              placeholder="Анна"
              aria-invalid={Boolean(errors.name)}
              {...register("name")}
            />
            <FieldError errors={[errors.name]} />
          </Field>

          <Field data-invalid={Boolean(errors.email)}>
            <FieldLabel htmlFor="email">Email</FieldLabel>
            <Input
              id="email"
              type="email"
              placeholder="anna@company.com"
              aria-invalid={Boolean(errors.email)}
              {...register("email")}
            />
            <FieldError errors={[errors.email]} />
          </Field>
        </div>

        <Field data-invalid={Boolean(errors.context)}>
          <FieldLabel htmlFor="context">Что будем строить?</FieldLabel>
          <Textarea
            id="context"
            placeholder="Коротко опишите первый продуктовый сценарий"
            aria-invalid={Boolean(errors.context)}
            {...register("context")}
          />
          <FieldDescription>От 10 до 400 символов.</FieldDescription>
          <FieldError errors={[errors.context]} />
        </Field>

        <Button className="w-full sm:w-fit" disabled={isSubmitting} size="lg" type="submit">
          {isSubmitting ? <Send className="animate-pulse" /> : <ArrowRight />}
          {isSubmitting ? "Отправляем" : "Проверить сценарий"}
        </Button>
      </FieldGroup>
    </form>
  )
}
