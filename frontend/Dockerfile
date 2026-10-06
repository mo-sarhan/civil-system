# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# Frontend: build the static bundle, then serve it from nginx.
# The image contains no runtime secrets; every value it needs is baked in at
# build time or handled by the nginx proxy.
# ---------------------------------------------------------------------------

FROM node:24-alpine AS build
WORKDIR /app

# Install against the lockfile first so dependency layers stay cacheable.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
