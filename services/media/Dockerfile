# Build from repo root: docker build -f services/media/Dockerfile .
FROM python:3.11-slim

WORKDIR /app

# Install deps: shared + media
COPY shared/ /app/shared/
COPY services/media/ /app/services/media/

RUN pip install --no-cache-dir -e /app/shared && \
    grep -v "^-e" /app/services/media/requirements.txt > /tmp/req.txt && \
    pip install --no-cache-dir -r /tmp/req.txt

ENV PYTHONPATH=/app:/app/services/media

WORKDIR /app/services/media
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
