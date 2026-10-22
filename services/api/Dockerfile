FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libraqm0 && rm -rf /var/lib/apt/lists/*
COPY services/api/pyproject.toml ./
COPY services/api/app ./app
RUN pip install --no-cache-dir ".[dev]"
COPY services/api/alembic.ini ./
COPY services/api/alembic ./alembic
COPY services/api/tests ./tests
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
