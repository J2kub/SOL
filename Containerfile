# syntax=docker/dockerfile:1

# ── check: code quality tools (Ruff/Mypy + ESLint) ─────────────────
FROM node:24-alpine AS check
RUN apk add --no-cache python3 py3-pip python3-dev bash
# Python tools
RUN pip install --no-cache-dir --break-system-packages ruff mypy
# TS tools — install into /app
WORKDIR /app
COPY tester/package*.json ./
RUN npm ci
# Entry point: bash (required by the spec)
ENTRYPOINT ["bash"]

# ── build: compile TypeScript tester ─────────────────────────────
FROM node:24-alpine AS build
WORKDIR /app
COPY tester/package*.json ./
RUN npm ci
COPY tester/src ./src
COPY tester/tsconfig.json ./
RUN ./node_modules/.bin/tsc --project tsconfig.json

# ── build-test: alias for build (backwards compatibility) ──────────
FROM build AS build-test

# ── runtime: interpreter (minimal image) ────────────────────────
FROM python:3.13-alpine AS runtime
WORKDIR /int/src
COPY int/src ./
COPY int/requirements.txt /int/requirements.txt
RUN pip install --no-cache-dir -r /int/requirements.txt
ENV PYTHONPATH=/int/src
ENTRYPOINT ["python3", "solint.py"]

# ── test: tester + interpreter ─────────────────────────────────
FROM runtime AS test
# Copy compiled tester from build stage
COPY --from=build /app/dist /tester/dist
COPY --from=build /app/node_modules /tester/node_modules
# Node.js to run the tester
RUN apk add --no-cache nodejs
ENV PYTHONPATH=/int/src
WORKDIR /tester
ENTRYPOINT ["node", "dist/tester.js"]
