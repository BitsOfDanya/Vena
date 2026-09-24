import Link from "next/link"

export function DashboardPage() {
  return (
    <div className="flex size-full flex-col items-start justify-center gap-4 px-8">
      <p className="text-[12px] font-medium tracking-[0.14em] text-faint uppercase">Dashboard</p>
      <h1 className="text-[26px] font-semibold tracking-[-0.01em]">Operational analytics workspace</h1>
      <p className="max-w-lg text-[14px] text-muted-foreground">
        Экран аналитики находится в разработке. Этот раздел будет подключён отдельно.
      </p>
      <Link
        href="/network"
        className="mt-1 text-[14px] text-vena underline-offset-4 hover:underline focus-visible:ring-2 focus-visible:ring-ring/60 focus-visible:outline-none"
      >
        Вернуться к схеме сети
      </Link>
    </div>
  )
}
