# syntax=docker/dockerfile:1

# ── check: nástroje kvality kódu (Ruff/Mypy + ESLint) ──────────────
FROM node:24-alpine AS check
RUN apk add --no-cache python3 py3-pip python3-dev bash
# Python nástroje
RUN pip install --no-cache-dir --break-system-packages ruff mypy
# TS nástroje — nainštaluj do /app (tester sa pripojí cez bind mount)
WORKDIR /app
COPY typescript/tester/package*.json ./
RUN npm ci
# Vstupný bod: bash (zadanie vyžaduje interaktívny shell)
ENTRYPOINT ["bash"]

# ── build: preklad TypeScript testera ───────────────────────────────
FROM node:24-alpine AS build
WORKDIR /app
COPY typescript/tester/package*.json ./
RUN npm ci
COPY typescript/tester/src ./src
COPY typescript/tester/tsconfig.json ./
RUN ./node_modules/.bin/tsc --project tsconfig.json

# ── build-test: alias pre build (pre spätnu kompatibilitu) ──────────
FROM build AS build-test

# ── runtime: interpret (čo najľahší obraz) ──────────────────────────
FROM python:3.13-alpine AS runtime
WORKDIR /int/src
COPY python/int/src ./
COPY python/int/requirements.txt /int/requirements.txt
RUN pip install --no-cache-dir -r /int/requirements.txt
ENV PYTHONPATH=/int/src
ENTRYPOINT ["python3", "solint.py"]

# ── test: tester + interpret ─────────────────────────────────────────
FROM runtime AS test
# Skopíruj preložený tester zo build
COPY --from=build /app/dist /tester/dist
COPY --from=build /app/node_modules /tester/node_modules
# Node.js pre spustenie testera
RUN apk add --no-cache nodejs
ENV PYTHONPATH=/int/src
WORKDIR /tester
ENTRYPOINT ["node", "dist/tester.js"]
