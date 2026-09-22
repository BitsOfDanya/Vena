# Vena frontend

Next.js App Router application organized with Feature-Sliced Design.

## Layers

```text
src/
├── app/       Next.js routes and providers
├── views/     FSD Pages layer (renamed to avoid Next.js Pages Router)
├── widgets/   Composed interface sections
├── features/  User interactions and use cases
├── entities/  Domain data and contracts
└── shared/    API client, utilities, and UI kit
```

The dependency direction is `app → views → widgets → features → entities → shared`.

## Commands

```bash
pnpm dev
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

Copy `.env.example` to `.env.local` before local development.

## Interface

Routes: `/pulse` (what needs attention now), `/network` (schematic state and asset table), `/timeline` (history and forecast around NOW), `/actions` (maintenance lifecycle), `/dashboard` (separate analytics module), `/settings`, `/settings/notifications`, `/settings/integrations`.

Operational chain: risk → alert → acknowledge → investigate → action → result. Notifications live in the header bell; a global notice bar appears only when `getSystemNotices()` returns a problem (empty by default).

- Map mode requires real spatial data (GeoJSON/WKT). It is intentionally not fabricated; the network schematic groups assets only by available data.
- The Dashboard module is reserved for separate implementation. Pulse, Network, Timeline and Actions do not depend on Dashboard components.
- The demo data adapter lives in `src/entities/infrastructure/data` and is reached only through service functions (`getPulse`, `getNetwork`, `getAsset`, `getRiskHistory`, `getEvents`, `getForecast`); actions go through a repository in `src/entities/maintenance/api`. Both can be replaced with REST clients.
- Risk is shown as a risk score out of 100 and is not presented as a probability until a calibrated score is available.

## Notification and action contracts

`entities/notification` describes `Notification`, `SystemNotice`, channels, rules and digest schedules; `entities/maintenance` describes the action lifecycle (`suggested → planned → assigned → in_progress → waiting → completed | cancelled`), audit history and outcomes. Both are served by local repositories that can be replaced with REST clients. Email delivery is not implemented in the frontend: the UI only records the requested channel and shows channel state.
