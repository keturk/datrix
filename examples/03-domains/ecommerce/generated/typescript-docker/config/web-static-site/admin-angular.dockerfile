# ---- Build stage ----
FROM node:24.21.0-alpine AS build

WORKDIR /app

# Install dependencies first (layer caching). Exec-form RUN (a JSON array,
# never a shell string) so an argv element can never be reinterpreted by a
# shell -- both argv lists are the web client target's own declared build
# step (ClientTargetCapabilityDeclaration.web_build), not authored here.
# The lockfile is copied with the manifest: a reproducible install (`npm ci`)
# refuses to run without it, and a build context missing it fails here, at
# COPY, naming the file -- never later with a resolved-at-build dependency set.
COPY package.json package-lock.json ./
RUN ["npm", "ci"]

# Copy application source and run the framework's own production build.
COPY . .
RUN ["npx", "ng", "build", "admin", "--configuration", "production"]

# ---- Serve stage ----
FROM nginx:1.30.5-alpine AS serve

# The built bundle only -- no node_modules, no source, no build tooling ships
# in the served image, and no per-profile value is baked in here: the
# deploy step writes the environment's own bootstrap config beside the
# bundle at deploy time, after the image is already built.
COPY --from=build /app/dist/admin/browser/ /usr/share/nginx/html/

# nginx.conf is NOT copied here -- the compose service mounts it read-only,
# the same pattern the gateway's own nginx.conf already uses, so a
# header-only change never forces a rebuild of the build stage above.

EXPOSE 80
