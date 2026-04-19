# syntax=docker/dockerfile:1

# ── check: nástroje kvality kódu ─────────────────────────────────
FROM node:24-alpine AS check
RUN apk add --no-cache python3 py3-pip python3-dev bash
RUN pip install --no-cache-dir --break-system-packages ruff mypy
WORKDIR /src/tester
COPY typescript/tester/package*.json ./
RUN npm ci
ENV PATH="/src/tester/node_modules/.bin:$PATH"
ENTRYPOINT ["bash"]

# ── build-test: prekladač TypeScript testera ──────────────────────
FROM node:24-alpine AS build-test
WORKDIR /app
COPY typescript/tester/package*.json ./
RUN npm ci
COPY typescript/tester/src ./src
COPY typescript/tester/tsconfig.json ./
RUN ./node_modules/.bin/tsc --project tsconfig.json

# ── runtime: interpreter ─────────────────────────────────────────
FROM python:3.14-rc-slim AS runtime
WORKDIR /int/src
COPY python/int/src ./
COPY python/int/requirements.txt /int/requirements.txt
RUN pip install --no-cache-dir -r /int/requirements.txt
ENV PYTHONPATH=/int/src
ENTRYPOINT ["python3", "solint.py"]

# ── test: tester + interpreter + sol2xml ─────────────────────────
FROM runtime AS test
RUN apt-get update && apt-get install -y \
    nodejs gcc \
    libxml2-dev libxslt1-dev \
    python3-lxml \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build-test /app/dist /tester/dist
COPY --from=build-test /app/node_modules /tester/node_modules
COPY sol2xml/ /sol2xml/
RUN pip install --no-cache-dir lark==1.2.2
RUN echo '#!/bin/sh' > /usr/local/bin/sol2xml && \
    echo 'exec python3 /sol2xml/sol_to_xml.py "$@"' >> /usr/local/bin/sol2xml && \
    chmod +x /usr/local/bin/sol2xml
ENV PYTHONPATH=/int/src
WORKDIR /tester
ENTRYPOINT ["node", "dist/tester.js"]