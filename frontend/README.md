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
pnpm build
```

Copy `.env.example` to `.env.local` before local development.
