# Vena agent rules

Read `.agents/skills/vena-fullstack/SKILL.md` before changing application code or architecture.

For frontend work, also read `.agents/skills/react-best-practices/SKILL.md` and the relevant local Next.js guide referenced by `frontend/AGENTS.md`. For backend work, also read `backend/.agents/skills/fastapi/SKILL.md` and only the linked reference needed by the task.

Use pnpm in `frontend/` and uv in `backend/`. Preserve the FSD dependency direction and keep Next.js route files thin. Keep shadcn/Radix components in `frontend/src/shared/ui` and style them through semantic tokens in `frontend/src/app/globals.css`.

Before handing off code, run the checks documented in the Vena skill for each changed surface. Do not modify the root `main.py` unless the task explicitly requests it.
