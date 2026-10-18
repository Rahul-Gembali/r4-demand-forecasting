# =============================================================================
# R4 Cold-Start Forecasting Dashboard - Frontend Multi-Stage Dockerfile
# Stage 1: TypeScript compilation and Vite build
# Stage 2: Lightweight Alpine Nginx server
# =============================================================================

# --- Stage 1: Build ---
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies strictly matching package-lock
COPY package.json package-lock.json ./
RUN npm ci

# Copy source and config files
COPY tsconfig.json vite.config.ts index.html ./
COPY src/ ./src/

# Compile TypeScript and bundle assets with Vite
RUN npm run build

# --- Stage 2: Production Nginx Runtime ---
FROM nginx:1.27-alpine AS runner

# Remove default nginx welcome page
RUN rm -rf /usr/share/nginx/html/*

# Copy built distribution from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

# Health check to ensure Nginx is serving content
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q --spider http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
