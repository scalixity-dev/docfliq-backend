# Build from repo root: docker build -f services/identity/Dockerfile .
FROM python:3.11-slim

WORKDIR /app

# Install deps: shared + identity
COPY shared/ /app/shared/
COPY services/identity/ /app/services/identity/

RUN pip install --no-cache-dir -e /app/shared && \
    grep -v "^-e" /app/services/identity/requirements.txt > /tmp/req.txt && \
    pip install --no-cache-dir -r /tmp/req.txt

# Override requirements so we use local shared (already in image)
ENV PYTHONPATH=/app:/app/services/identity

WORKDIR /app/services/identity
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
