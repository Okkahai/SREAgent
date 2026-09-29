FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
RUN pip install .
RUN useradd --system --uid 10001 opspilot
USER opspilot
EXPOSE 8000
CMD ["uvicorn", "opspilot.main:app", "--host", "0.0.0.0", "--port", "8000"]
