# syntax=docker/dockerfile:1

# ── check: nástroje kvality kódu (Ruff/Mypy + ESLint/Prettier) ──
FROM node:24-alpine AS check
RUN apk add --no-cache python3 py3-pip python3-dev
WORKDIR /app
# TS nástroje
COPY typescript/tester/package*.json ./
RUN npm ci
# Python nástroje — nainštaluj Ruff a Mypy
RUN pip install --no-cache-dir ruff mypy
# Bind mount sa použije za behu (src/int, src/tester)
# Vstupný bod: bash (zadanie vyžaduje bash v check stage)
ENTRYPOINT ["bash"]

# ── build-test: preklad TypeScript testera ──
FROM node:24-alpine AS build-test
WORKDIR /app
COPY typescript/tester/package*.json ./
RUN npm ci
COPY typescript/tester/src ./src
COPY typescript/tester/tsconfig.json ./
RUN npm run build

# ── runtime: interpret (čo najľahší obraz) ──
FROM python:3.13-alpine AS runtime
WORKDIR /int/src
COPY python/int/src ./
COPY python/int/requirements.txt /int/requirements.txt
RUN pip install --no-cache-dir -r /int/requirements.txt
ENV PYTHONPATH=/int/src
ENTRYPOINT ["python3", "solint.py"]

# ── test: spustenie testera ──
FROM runtime AS test
# Skopíruj preložený tester zo build-test
COPY --from=build-test /app/dist /app/dist
COPY --from=build-test /app/node_modules /app/node_modules
# Node.js potrebujeme v runtime obraze pre spustenie testera
RUN apk add --no-cache nodejs
# SOL2XML sa pripojí ako bind mount
ENV PYTHONPATH=/int/src
WORKDIR /app
ENTRYPOINT ["node", "dist/tester.js"]