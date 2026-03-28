# ---- Builder stage ----
FROM node:22-alpine AS builder

WORKDIR /app

# Install dependencies first (layer caching)
COPY package.json package-lock.json* ./
RUN npm ci || npm install

# Copy application source and build
COPY src/ ./src/
COPY tsconfig.json* ./
RUN npm run build

# ---- Runtime stage ----
FROM node:22-alpine AS runtime

WORKDIR /app

# Copy built application and dependencies
COPY --from=builder /app/node_modules/ ./node_modules/
COPY --from=builder /app/dist/ ./dist/

# Set environment variables
ENV PORT=8001
ENV SERVICE_NAME=ecommerce-product-service

# Expose service port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:8001/health || exit 1

# Switch to non-root user (node user is built into the node:*-alpine image)
USER node

# Run the application
CMD ["node", "dist/main.js"]
