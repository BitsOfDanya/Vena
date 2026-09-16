# Vena

Full-stack foundation with FastAPI and Next.js.

## Stack

- FastAPI, Pydantic Settings, uv, Ruff, mypy, pytest
- Next.js App Router, React, TypeScript, Tailwind CSS
- Feature-Sliced Design (`views` is the Pages layer)
- shadcn/ui on Radix UI with a custom light theme
- TanStack Query, React Hook Form, Zod

## Local development

Start the API:

```bash
cd backend
cp .env.example .env
uv sync
uv run fastapi dev
```

Start the web app in a second terminal:

```bash
cd frontend
cp .env.example .env.local
pnpm install
pnpm dev
```

Open `http://localhost:3000`. API docs are available at `http://localhost:8000/docs`, and the component inventory is at `http://localhost:3000/design-system`.

## Checks

```bash
cd backend && uv run ruff check . && uv run mypy app && uv run pytest
cd frontend && pnpm lint && pnpm build
```
