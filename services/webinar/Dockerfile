FROM python:3.11-slim
WORKDIR /app
COPY shared/ /app/shared/
COPY services/webinar/ /app/services/webinar/
RUN pip install --no-cache-dir -e /app/shared && \
    grep -v "^-e" /app/services/webinar/requirements.txt > /tmp/req.txt && \
    pip install --no-cache-dir -r /tmp/req.txt
ENV PYTHONPATH=/app:/app/services/webinar
WORKDIR /app/services/webinar
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
