import { z } from "zod"

export function accessSchema(mode: "login" | "register") {
  return z.object({
    full_name: mode === "register" ? z.string().trim().min(2, "Укажите имя") : z.string(),
    email: z.email("Введите корректный email"),
    password: mode === "register"
      ? z.string().min(10, "Минимум 10 символов")
      : z.string().min(1, "Введите пароль"),
    role: z.enum(["operator", "dispatcher"]),
    invite_code: z.string(),
  })
}

export type AccessValues = z.infer<ReturnType<typeof accessSchema>>
