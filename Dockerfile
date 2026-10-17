# AnnRakshak, as one image: the farmer app, the officer console and the API.
#
# One origin on purpose. The browser app and the API behind the same host means
# the session cookie is a first-party cookie, no CORS is involved at all, and
# the /media photographs are fetched with the viewer's own session — which is
# what makes them private. Split them across two domains and you need
# ANNRAKSHAK_ORIGINS, and you are responsible for the cookie reaching back.
#
#   docker build -t annrakshak .
#   docker run --env-file .env -p 8010:8010 \
#     -v "$PWD/ml/artifacts:/app/ml/artifacts:ro" -v annrakshak-data:/data annrakshak
#
# The trained model is not in the image: it is 80 MB of weights that change on
# their own schedule, so it is mounted. Without it the API serves the labelled
# stub and says so in /health — it starts, it just will not pretend to diagnose.

# ---------------------------------------------------------------- the app ---
FROM node:22-alpine AS web
WORKDIR /build
COPY package.json package-lock.json ./
COPY frontend/landing/package.json frontend/landing/
COPY frontend/farmer-app/package.json frontend/farmer-app/
COPY frontend/officer-dashboard/package.json frontend/officer-dashboard/
RUN npm ci --workspaces --include-workspace-root
COPY frontend/ frontend/
RUN npm run build -w frontend/landing

# ------------------------------------------------------------- the server ---
FROM python:3.12-slim AS api
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ANNRAKSHAK_ENV=production \
    ANNRAKSHAK_DATA_DIR=/data \
    ANNRAKSHAK_WEB_DIR=/app/web

WORKDIR /app

# curl for the health check; the rest of the image stays slim. torch comes from
# the CPU index: the GPU build is gigabytes and this server never trains.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu \
    -r backend/requirements.txt

COPY backend/ backend/
COPY --from=web /build/frontend/landing/dist/ web/

# Not root: a bug in a photo parser should not own the container.
RUN useradd --system --uid 10001 annrakshak \
    && mkdir -p /data && chown -R annrakshak:annrakshak /data /app
USER annrakshak

EXPOSE 8010
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8010/health || exit 1

# One worker by design: the background watcher must run in exactly one process
# or every farmer gets each alert twice. Scale by running more containers with
# ANNRAKSHAK_WATCH=off on all but one.
# No --proxy-headers: uvicorn would rewrite the client address from a header
# the caller can write, which is the per-IP limit gone. Whether to believe
# X-Forwarded-For is one decision and it is ANNRAKSHAK_TRUST_PROXY's, made by
# whoever actually put a proxy in front.
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8010"]
