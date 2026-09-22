FROM node:22-alpine AS deps
WORKDIR /srv/app
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM node:22-alpine AS build
WORKDIR /srv/app
RUN corepack enable
ENV NEXT_TELEMETRY_DISABLED=1
ARG NEXT_PUBLIC_API_URL=http://localhost:8100
ARG NEXT_PUBLIC_VENA_DATA_MODE=demo
ARG NEXT_PUBLIC_VENA_WORKFLOW_MODE=demo
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
RUN corepack enable
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=build /srv/app/node_modules ./node_modules
COPY --from=build /srv/app/.next ./.next
COPY --from=build /srv/app/package.json ./package.json
COPY --from=build /srv/app/next.config.ts ./next.config.ts
EXPOSE 3000
CMD ["pnpm", "start", "--port", "3000", "--hostname", "0.0.0.0"]
