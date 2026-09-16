"use client"

import { ArrowLeft, Bell, CheckCircle2, Info, Sparkles } from "lucide-react"
import Link from "next/link"

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/shared/ui/accordion"
import { Alert, AlertDescription, AlertTitle } from "@/shared/ui/alert"
import { Badge } from "@/shared/ui/badge"
import { Button } from "@/shared/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/ui/card"
import { Checkbox } from "@/shared/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/shared/ui/dialog"
import { Field, FieldLabel } from "@/shared/ui/field"
import { Input } from "@/shared/ui/input"
import { Progress } from "@/shared/ui/progress"
import { Separator } from "@/shared/ui/separator"
import { Slider } from "@/shared/ui/slider"
import { Switch } from "@/shared/ui/switch"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/tabs"
import { Textarea } from "@/shared/ui/textarea"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/shared/ui/tooltip"

const componentInventory = [
  "Accordion", "Alert", "Alert Dialog", "Aspect Ratio", "Attachment", "Avatar",
  "Badge", "Breadcrumb", "Bubble", "Button", "Button Group", "Calendar", "Card",
  "Carousel", "Chart", "Checkbox", "Collapsible", "Combobox", "Command",
  "Context Menu", "Dialog", "Direction", "Drawer", "Dropdown Menu", "Empty",
  "Field", "Hover Card", "Input", "Input Group", "Input OTP", "Item", "Kbd",
  "Label", "Marker", "Menubar", "Message", "Message Scroller", "Native Select",
  "Navigation Menu", "Pagination", "Popover", "Progress", "Questionnaire",
  "Radio Group", "Resizable", "Scroll Area", "Select", "Separator", "Sheet",
  "Sidebar", "Skeleton", "Slider", "Sonner", "Spinner", "Switch", "Table",
  "Tabs", "Textarea", "Toggle", "Toggle Group", "Tooltip",
]

const colors = [
  { name: "Primary", className: "bg-primary" },
  { name: "Secondary", className: "bg-secondary" },
  { name: "Accent", className: "bg-accent" },
  { name: "Muted", className: "bg-muted" },
  { name: "Destructive", className: "bg-destructive" },
]

export function DesignSystemPage() {
  return (
    <main className="mx-auto min-h-svh w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      <div className="mb-10 flex items-center justify-between">
        <Button asChild variant="ghost">
          <Link href="/"><ArrowLeft /> На главную</Link>
        </Button>
        <Badge variant="secondary">61 components</Badge>
      </div>

      <section className="mb-14 max-w-3xl">
        <Badge className="mb-4" variant="outline">
          <Sparkles data-icon="inline-start" /> Vena UI
        </Badge>
        <h1 className="font-heading text-4xl font-semibold tracking-[-0.04em] sm:text-6xl">Светлая, спокойная, системная.</h1>
        <p className="mt-5 max-w-2xl text-lg leading-8 text-muted-foreground">
          Токены Vena поверх доступных Radix-примитивов. Компоненты принадлежат проекту, поэтому их можно менять вместе с продуктом.
        </p>
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Цветовые токены</CardTitle>
            <CardDescription>OKLCH-палитра с мягким cyan-акцентом.</CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            {colors.map((color) => (
              <div key={color.name}>
                <div className={`mb-2 aspect-square rounded-xl border shadow-inner ${color.className}`} />
                <p className="text-xs text-muted-foreground">{color.name}</p>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Действия</CardTitle>
            <CardDescription>Варианты и состояния кнопок.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap items-center gap-3">
            <Button>Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="outline">Outline</Button>
            <Button variant="ghost">Ghost</Button>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button aria-label="Уведомления" size="icon" variant="outline"><Bell /></Button>
              </TooltipTrigger>
              <TooltipContent>Уведомления</TooltipContent>
            </Tooltip>
            <Button disabled>Disabled</Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Поля и контролы</CardTitle>
            <CardDescription>Единые focus, invalid и disabled состояния.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field><FieldLabel htmlFor="sample-name">Название</FieldLabel><Input id="sample-name" placeholder="Новый сценарий" /></Field>
              <Field><FieldLabel htmlFor="sample-email">Email</FieldLabel><Input id="sample-email" type="email" defaultValue="team@vena.dev" /></Field>
            </div>
            <Textarea aria-label="Комментарий" placeholder="Комментарий" />
            <div className="flex flex-wrap gap-6">
              <Field orientation="horizontal"><Switch defaultChecked id="updates" /><FieldLabel htmlFor="updates">Обновления</FieldLabel></Field>
              <Field orientation="horizontal"><Checkbox defaultChecked id="terms" /><FieldLabel htmlFor="terms">Согласие</FieldLabel></Field>
            </div>
            <Slider defaultValue={[62]} max={100} step={1} aria-label="Прогресс настройки" />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Состояния</CardTitle>
            <CardDescription>Обратная связь остаётся заметной, но спокойной.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Alert>
              <Info />
              <AlertTitle>Информационное сообщение</AlertTitle>
              <AlertDescription>Используйте для контекста, который не блокирует действие.</AlertDescription>
            </Alert>
            <Alert className="border-emerald-200 bg-emerald-50/70 text-emerald-900">
              <CheckCircle2 />
              <AlertTitle>Готово к работе</AlertTitle>
              <AlertDescription className="text-emerald-800/75">Компоненты установлены и используют общие токены.</AlertDescription>
            </Alert>
            <div>
              <div className="mb-2 flex justify-between text-sm"><span>Готовность основы</span><span className="text-muted-foreground">84%</span></div>
              <Progress value={84} />
            </div>
          </CardContent>
        </Card>
      </div>

      <section className="py-12">
        <Tabs defaultValue="patterns">
          <TabsList>
            <TabsTrigger value="patterns">Паттерны</TabsTrigger>
            <TabsTrigger value="inventory">Инвентарь</TabsTrigger>
          </TabsList>
          <TabsContent className="pt-5" value="patterns">
            <div className="grid gap-5 lg:grid-cols-[1fr_auto]">
              <Card>
                <CardHeader><CardTitle>Раскрывающийся контент</CardTitle></CardHeader>
                <CardContent>
                  <Accordion collapsible type="single">
                    <AccordionItem value="ownership">
                      <AccordionTrigger>Кому принадлежат компоненты?</AccordionTrigger>
                      <AccordionContent>Они скопированы в shared/ui и версионируются вместе с приложением.</AccordionContent>
                    </AccordionItem>
                    <AccordionItem value="radix">
                      <AccordionTrigger>Где используется Radix?</AccordionTrigger>
                      <AccordionContent>В интерактивных примитивах: dialog, tooltip, tabs, menu и других.</AccordionContent>
                    </AccordionItem>
                  </Accordion>
                </CardContent>
              </Card>
              <Dialog>
                <DialogTrigger asChild><Button variant="outline">Открыть dialog</Button></DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Готовый интерактивный паттерн</DialogTitle>
                    <DialogDescription>Фокус, клавиатура и aria-поведение приходят из Radix UI.</DialogDescription>
                  </DialogHeader>
                  <DialogFooter showCloseButton />
                </DialogContent>
              </Dialog>
            </div>
          </TabsContent>
          <TabsContent className="pt-5" value="inventory">
            <Card>
              <CardHeader>
                <CardTitle>Полный локальный набор</CardTitle>
                <CardDescription>Все доступные компоненты официального shadcn registry добавлены в shared/ui.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-x-5 gap-y-2 text-sm sm:grid-cols-3 lg:grid-cols-5">
                  {componentInventory.map((component) => (
                    <div className="flex items-center gap-2 py-1.5" key={component}>
                      <span className="size-1.5 rounded-full bg-primary" />{component}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </section>

      <Separator />
      <footer className="py-6 text-sm text-muted-foreground">Vena design system · Tailwind CSS · shadcn/ui · Radix UI</footer>
    </main>
  )
}
