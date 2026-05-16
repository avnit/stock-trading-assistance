FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build


FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ARGO_DATA_DIR=/tmp/argo

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

# Drop the built React SPA into the package so StaticFiles can find it.
COPY --from=frontend /fe/dist ./src/argo/static/ui

RUN pip install --upgrade pip \
 && pip install ".[server]"

RUN useradd --create-home --uid 1000 argo \
 && mkdir -p /tmp/argo \
 && chown -R argo:argo /tmp/argo
USER argo

EXPOSE 8080

CMD exec uvicorn argo.server:app --host 0.0.0.0 --port ${PORT:-8080}
