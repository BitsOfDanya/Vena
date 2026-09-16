---
name: vena-fullstack
description: Build and change the Vena application using its FastAPI backend, Next.js App Router frontend, Feature-Sliced Design boundaries, and shared light UI system. Use for implementation, refactoring, architecture, API integration, forms, or UI work in this repository.
---

# Vena full-stack conventions

Use these repository-specific decisions together with the framework skills installed in this project. Do not turn them into global preferences for unrelated repositories.

## Repository shape

- `backend/` is the FastAPI service managed with uv.
- `frontend/` is the Next.js App Router application managed with pnpm.
- Keep `ml/` and `infra/` independent until a task gives them a concrete responsibility.
- Do not use or rewrite the root `main.py`; it is legacy IDE scaffolding unless a task explicitly brings it into scope.

## Frontend architecture

Use the dependency direction `app → views → widgets → features → entities → shared`. A lower layer must not import a higher layer. Avoid cross-imports between slices on the same layer.

Next.js owns `frontend/src/app`, so it is the routing and provider layer. Use `frontend/src/views` as the FSD Pages layer to avoid activating the legacy Next.js Pages Router through `src/pages`.

Each business slice exposes a small public API through `index.ts`. Import generated design-system components directly from `@/shared/ui/<component>` rather than adding a broad UI barrel. Keep route files thin: they compose and export a view, while product logic belongs in FSD slices.

Default to Server Components. Add `"use client"` only at the smallest boundary that needs state, effects, event handlers, React Hook Form, TanStack Query, or a client-only primitive.

Use TanStack Query for client-side server state, with stable tuple query keys grouped by entity. Treat response JSON as `unknown` and validate it with Zod before it enters the application. Keep forms inside a feature; put their Zod schema in `model/` and connect it with `zodResolver` and React Hook Form.

## Design system

- The source of truth is `frontend/src/shared/ui`, generated from shadcn/ui on Radix primitives.
- Theme tokens belong in `frontend/src/app/globals.css`; prefer semantic tokens over raw colors in components.
- Keep the default experience light, calm, high-contrast, keyboard accessible, and responsive.
- Extend local components when product needs diverge; do not install a second component library for an equivalent primitive.
- The `/design-system` route is the visible inventory and should be updated when foundational tokens or component conventions change.

## Backend architecture

Keep the FastAPI entrypoint in `backend/app/main.py`, settings in `app/core`, and versioned routers under `app/api`. Put router prefixes and tags on `APIRouter` instances. Return typed Pydantic models and keep transport schemas close to the owning route or domain until a repeated domain warrants a dedicated package.

Use synchronous path functions for blocking or purely synchronous logic, and `async def` only when the implementation awaits non-blocking I/O. Add tests for every new route. Do not choose a database, migration tool, auth scheme, task queue, or deployment target without a product requirement.

## Definition of done

Run the checks for the surface changed:

```bash
cd backend && uv run ruff check . && uv run mypy app && uv run pytest
cd frontend && pnpm lint && pnpm build
```

Update `.env.example` when configuration changes. Never commit real secrets or local `.env` files.
