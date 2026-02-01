FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV PORT=8080

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        poppler-utils \
        libglib2.0-0 \
        libgomp1 \
        libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY app /app
COPY tools /app/tools
COPY templates_draft /app/templates_draft

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

EXPOSE 8080
CMD ["sh", "-c", "uvicorn fichas.main:app --host 0.0.0.0 --port ${PORT}"]
