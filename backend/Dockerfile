FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv/backend

# --- dependencies (cached layer) ---
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- application code ---
# Layout must mirror the repo:  <root>/backend/app  +  <root>/config.yaml
# so that app.config resolves DATA_DIR -> /srv/data and CONFIG_YAML_PATH -> /srv/config.yaml
COPY backend/app ./app
COPY backend/scripts ./scripts
COPY config.yaml /srv/config.yaml

RUN mkdir -p /srv/data
VOLUME ["/srv/data"]

EXPOSE 8000

# Single worker: research runs keep in-process state (LangGraph + event bus)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
