# ---- Builder stage ----
FROM node:22-alpine AS builder

WORKDIR /app

# Enable pnpm via corepack (built into Node.js)
RUN corepack enable

# Install dependencies first (layer caching).
# No lockfile is emitted by codegen; copying a workspace lockfile can drift from
# per-service package.json. Install from the manifest only.
COPY package.json ./
RUN pnpm install --shamefully-hoist

# Copy application source and build
COPY src/ ./src/
COPY tsconfig.json* ./
RUN pnpm run build

# Remove devDependencies — runtime image only needs production deps
RUN pnpm prune --prod

# ---- Runtime stage ----
FROM node:22-alpine AS runtime

WORKDIR /app

# Copy built application and dependencies
COPY --from=builder /app/node_modules/ ./node_modules/
COPY --from=builder /app/dist/ ./dist/

# Set environment variables
ENV PORT=8001
ENV SERVICE_NAME=examples-order-service

# Expose service port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:8001/ready || exit 1

# Switch to non-root user (node user is built into the node:*-alpine image)
USER node

# Run the application
CMD ["node", "dist/main.js"]
