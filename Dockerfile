# LayerHound in a container: the built dashboard and the backend, running as a non-root user.
# Everything that must survive an update (database, encryption key, files) lives in /data.
#   docker compose up -d          (see docker-compose.yml and the README's Docker section)

# ---- Build the dashboard ----
FROM node:22-slim AS web
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY index.html vite.config.js ./
COPY src ./src
COPY public ./public
RUN npm run build

# ---- Run it ----
FROM python:3.12-slim
# ping and ip: internet health, device monitoring and the network scan. tzdata: the TZ setting.
RUN apt-get update \
 && apt-get install -y --no-install-recommends iputils-ping iproute2 tzdata \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend backend
COPY --from=web /src/dist dist
COPY LICENSE TRADEMARKS.md README.md ./
# Manufacturer list for the network scan (the board downloads it during setup). Optional:
# the scan still works without it, just without manufacturer names.
RUN mkdir -p backend/data \
 && (python -c "import urllib.request as u; u.urlretrieve('https://standards-oui.ieee.org/oui/oui.csv','backend/data/oui.csv')" \
     || echo 'oui.csv not downloaded; device manufacturers will be blank')

RUN useradd --system --uid 1000 --home-dir /data layerhound \
 && mkdir -p /data && chown layerhound /data
USER layerhound
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LAYERHOUND_DOCKER=1 \
    LAYERHOUND_DB=/data/layerhound.db \
    LAYERHOUND_FILES=/data/files \
    LAYERHOUND_PORT=8080
VOLUME /data
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ['LAYERHOUND_PORT']+'/api/health', timeout=4)"
WORKDIR /app/backend
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port \"$LAYERHOUND_PORT\""]

LABEL org.opencontainers.image.title="LayerHound" \
      org.opencontainers.image.description="Print farm and home lab dashboard by Team Tactical RC" \
      org.opencontainers.image.source="https://github.com/TeamTacticalRC/LayerHound" \
      org.opencontainers.image.licenses="AGPL-3.0-only"
