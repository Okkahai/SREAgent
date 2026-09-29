FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml ./
COPY shop ./shop
RUN pip install .
RUN useradd --system --uid 10001 shop
USER shop
EXPOSE 8000
CMD ["uvicorn", "shop.gateway:app", "--host", "0.0.0.0", "--port", "8000"]
