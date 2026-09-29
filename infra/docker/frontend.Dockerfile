ARG VENA_NODE_IMAGE=node:22-alpine
FROM ${VENA_NODE_IMAGE} AS build
WORKDIR /srv/app
RUN npm install --global pnpm@10.9.0
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
ARG NEXT_PUBLIC_VENA_ENVIRONMENT=production
ENV NEXT_TELEMETRY_DISABLED=1 NEXT_PUBLIC_API_URL="" NEXT_PUBLIC_VENA_DATA_MODE=live NEXT_PUBLIC_VENA_WORKFLOW_MODE=api NEXT_PUBLIC_VENA_ENVIRONMENT=$NEXT_PUBLIC_VENA_ENVIRONMENT
RUN mkdir -p public && pnpm build

FROM ${VENA_NODE_IMAGE}
WORKDIR /srv/app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build --chown=node:node /srv/app/.next/standalone ./
COPY --from=build --chown=node:node /srv/app/.next/static ./.next/static
COPY --from=build --chown=node:node /srv/app/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
