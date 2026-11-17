# Sijill container image. Written as a deliverable; built in CI only.
# Stage 1: build the web interface
FROM node:24-alpine AS web
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npx vite build

# Stage 2: Python runtime serving API + built UI
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PDPL_DATA_DIR=/data \
    PDPL_FRONTEND_DIST=/app/frontend/dist
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY catalog/ catalog/
COPY compliance/ compliance/
COPY collectors/ collectors/
COPY --from=web /src/frontend/dist frontend/dist
RUN useradd --system --uid 10001 pdpl && mkdir -p /data && chown pdpl /data
USER pdpl
VOLUME ["/data"]
EXPOSE 8000
WORKDIR /app/backend
# PDPL_SEED_DEMO=1 loads the fictional demo clinic on first start.
CMD ["sh", "-c", "python -m app.cli migrate && if [ \"$PDPL_SEED_DEMO\" = \"1\" ]; then python -m app.cli seed-demo --if-empty; fi && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
