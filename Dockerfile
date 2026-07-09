# ---- Stage 1: build the React frontend into frontend/dist ----
FROM node:24-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend ./
RUN npm run build

# ---- Stage 2: Python runtime that serves the API + the built frontend ----
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# git is required at runtime — the scanner clones public repos with `git clone`.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY --from=frontend /app/frontend/dist ./frontend/dist

EXPOSE 8000
# The host injects $PORT (Render/Railway/Fly); default 8000 for local runs.
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
