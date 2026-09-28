# The app is built inside the image: NEXT_PUBLIC_* values are inlined at build
# time, so they come from compose build args, and native packages match Linux.
FROM node:22-alpine AS base
WORKDIR /srv/app
RUN npm install --global pnpm@10.9.0

FROM base AS deps
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM base AS build
ENV NEXT_TELEMETRY_DISABLED=1
ARG NEXT_PUBLIC_API_URL=http://localhost:8100
ARG NEXT_PUBLIC_VENA_DATA_MODE=demo
ARG NEXT_PUBLIC_VENA_WORKFLOW_MODE=api
ARG NEXT_PUBLIC_VENA_ENVIRONMENT=docker
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_VENA_DATA_MODE=$NEXT_PUBLIC_VENA_DATA_MODE \
    NEXT_PUBLIC_VENA_WORKFLOW_MODE=$NEXT_PUBLIC_VENA_WORKFLOW_MODE \
    NEXT_PUBLIC_VENA_ENVIRONMENT=$NEXT_PUBLIC_VENA_ENVIRONMENT
COPY --from=deps /srv/app/node_modules ./node_modules
COPY . .
RUN pnpm build

FROM node:22-alpine AS runtime
WORKDIR /srv/app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
# next.config.ts builds a standalone server with only the runtime dependencies.
COPY --from=build --chown=node:node /srv/app/.next/standalone ./
COPY --from=build --chown=node:node /srv/app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
