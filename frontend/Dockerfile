# Offline-friendly image: build on the host, then package artifacts.
# Requires a prior `pnpm build` with the same NEXT_PUBLIC_* values.
FROM node:22-slim AS runtime
WORKDIR /srv/app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1
COPY package.json next.config.ts ./
COPY node_modules ./node_modules
COPY .next ./.next
EXPOSE 3000
CMD ["node", "node_modules/next/dist/bin/next", "start", "--port", "3000", "--hostname", "0.0.0.0"]
