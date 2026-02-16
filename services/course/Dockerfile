FROM python:3.11-slim
WORKDIR /app
COPY shared/ /app/shared/
COPY services/course/ /app/services/course/
RUN pip install --no-cache-dir -e /app/shared && \
    grep -v "^-e" /app/services/course/requirements.txt > /tmp/req.txt && \
    pip install --no-cache-dir -r /tmp/req.txt
ENV PYTHONPATH=/app:/app/services/course
WORKDIR /app/services/course
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
