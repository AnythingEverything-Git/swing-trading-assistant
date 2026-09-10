# Production UI — static Vite build served by nginx (same Free Tier EC2 as API).
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Empty base URL → browser calls same origin (/api/...) via nginx proxy
ENV VITE_API_BASE_URL=
RUN chmod -R a+rx node_modules/.bin \
  && npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
