import * as z from "zod"

export const requestDemoSchema = z.object({
  name: z.string().trim().min(2, "Укажите имя"),
  email: z.email("Введите корректный email"),
  context: z
    .string()
    .trim()
    .min(10, "Добавьте немного контекста")
    .max(400, "Не больше 400 символов"),
})

export type RequestDemoValues = z.infer<typeof requestDemoSchema>
