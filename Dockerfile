# syntax=docker/dockerfile:1

# ---- Stage 1: builder ----
FROM python:3.11-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Stage 2: runtime ----
FROM python:3.11-slim AS runtime

RUN addgroup --system botgroup && adduser --system --ingroup botgroup botuser

WORKDIR /app

COPY --from=builder /install /usr/local

COPY --chown=botuser:botgroup . .

RUN mkdir -p data/logs && chown -R botuser:botgroup data /app

USER botuser

VOLUME ["/app/data"]

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
