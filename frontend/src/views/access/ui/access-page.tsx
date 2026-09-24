import { AccessForm } from "@/features/account-access"

export function AccessPage({ mode }: { mode: "login" | "register" }) {
  return (
    <main className="grid min-h-svh grid-cols-1 bg-background lg:grid-cols-[1fr_1fr]">
      <div className="hidden flex-col justify-between border-r border-border bg-sidebar p-12 lg:flex">
        <div className="text-2xl font-bold tracking-[0.15em] text-white"><span className="text-primary">V</span>ENA</div>
        <div className="max-w-lg space-y-5">
          <div className="inline-flex rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-primary">Infrastructure intelligence</div>
          <h1 className="text-5xl font-semibold leading-[1.1] tracking-tight text-white">Видеть риски.<br />Действовать раньше.</h1>
          <p className="max-w-md text-base leading-7 text-muted-foreground">Единое пространство для наблюдения за инженерными системами, прогнозов и работы диспетчера.</p>
        </div>
        <p className="text-sm text-faint">Vena · Москва · 2026</p>
      </div>
      <div className="flex min-h-svh flex-col items-center justify-center px-5 py-12">
        <div className="mb-8 text-xl font-bold tracking-[0.15em] lg:hidden"><span className="text-primary">V</span>ENA</div>
        <AccessForm mode={mode} />
      </div>
    </main>
  )
}
