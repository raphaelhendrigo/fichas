FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV PORT=8080

COPY app /app

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

EXPOSE 8080
CMD ["sh", "-c", "uvicorn fichas.main:app --host 0.0.0.0 --port ${PORT}"]
