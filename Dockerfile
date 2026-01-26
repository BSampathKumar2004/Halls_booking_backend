# -------------------------
# 1. Use official Python image
# -------------------------
FROM python:3.11-slim

# -------------------------
# 2. Set working directory
# -------------------------
WORKDIR /app

# -------------------------
# 3. Install system dependencies
# -------------------------
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# -------------------------
# 4. Install Python dependencies
# -------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# -------------------------
# 5. Copy application code
# -------------------------
COPY . .

# -------------------------
# 6. Copy environment variables
#    (Required for Alembic + backend inside Docker)
# -------------------------
COPY .env .env

# -------------------------
# 7. Copy Alembic entrypoint script
# -------------------------
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# -------------------------
# 8. Expose application port
# -------------------------
EXPOSE 8000

# -------------------------
# 9. Run Alembic + Start FastAPI
# -------------------------
ENTRYPOINT ["/entrypoint.sh"]

CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "--workers", "4", "--bind", "0.0.0.0:8000"]
