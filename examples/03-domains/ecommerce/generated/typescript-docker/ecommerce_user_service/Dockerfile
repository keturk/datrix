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

# Copy application source and build. nest-cli.json is what tells `nest build`
# to carry the emitted JSON sidecars under src/ into dist/; without it the
# runtime image, which copies dist/ alone, is missing files the service reads
# from its own compiled directory at startup.
COPY src/ ./src/
COPY tsconfig.json* ./
COPY nest-cli.json ./
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
ENV PORT=8006
ENV SERVICE_NAME=ecommerce-user-service

# Expose service port
EXPOSE 8006

# Health check: the language's own command against the readiness route the
# language declares it mounts (supplied by its LanguageRuntimeSpec.dockerfile_context).
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:8006/health || exit 1

# Switch to non-root user (node user is built into the node:*-alpine image)
USER node

# Run the application
CMD ["node", "dist/main.js"]
