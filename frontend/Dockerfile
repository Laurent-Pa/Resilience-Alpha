FROM node:20-alpine AS base

FROM base AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_ADMIN_API_BASE_URL
ENV NEXT_PUBLIC_ADMIN_API_BASE_URL=$NEXT_PUBLIC_ADMIN_API_BASE_URL
ARG NEXT_PUBLIC_OIDC_AUTHORITY
ENV NEXT_PUBLIC_OIDC_AUTHORITY=$NEXT_PUBLIC_OIDC_AUTHORITY
# Client Keycloak dédié au back-office (rôle ops requis) ; même realm que web-pay.
ARG NEXT_PUBLIC_ADMIN_OIDC_CLIENT_ID
ENV NEXT_PUBLIC_ADMIN_OIDC_CLIENT_ID=$NEXT_PUBLIC_ADMIN_OIDC_CLIENT_ID
# Service face-auth (habilitations biométriques du back-office).
ARG NEXT_PUBLIC_BIOMETRICS_API_BASE_URL
ENV NEXT_PUBLIC_BIOMETRICS_API_BASE_URL=$NEXT_PUBLIC_BIOMETRICS_API_BASE_URL
RUN npm run build

FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json

EXPOSE 3000
CMD ["npm", "start"]
