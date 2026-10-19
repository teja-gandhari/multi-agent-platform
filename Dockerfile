
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONNUNBUFFERED=1 \
    PYTHONPATH=/app/backend:/app/nexuxai_workflow

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
COPY nexuxai_workflow/requirements.txt /app/nexuxai_workflow/requirements.txt

# Install backend and LangGraph workflow dependencies
RUN pip install --no-cache-dir \
    -r /app/backend/requirements.txt \
    -r /app/nexuxai_workflow/requirements.txt

COPY backend /app/backend
COPY nexuxai_workflow /app/nexuxai_workflow

# Run FastAPI inside the container
EXPOSE 8000



CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "/app/backend"]
