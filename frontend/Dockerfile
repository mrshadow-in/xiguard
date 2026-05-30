FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --legacy-peer-deps

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
# Diagnostic — prove the right config files were copied into the image.
RUN echo "=== tsconfig.json ===" && cat tsconfig.json && \
    echo "=== next.config.js ===" && cat next.config.js && \
    echo "=== src/lib listing ===" && ls -la src/lib && \
    echo "=== test resolve ===" && \
    node -e "console.log(require('path').resolve(__dirname,'src','lib','api.ts'))"
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
