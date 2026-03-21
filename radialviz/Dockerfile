FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies
RUN pip install --no-cache-dir flask flask-cors gunicorn

# Copy the API server
COPY serve_api.py .

# Database lives on persistent Fly.io volume at /data
ENV DB_PATH=/data/greek_vocab.db

EXPOSE 8080

# Run with gunicorn for production (4 workers, read-only DB is safe for concurrency)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "120", "--graceful-timeout", "3", "serve_api:app"]
