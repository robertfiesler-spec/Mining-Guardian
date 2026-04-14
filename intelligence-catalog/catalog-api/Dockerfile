FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY catalog_api.py .

EXPOSE 8420

CMD ["uvicorn", "catalog_api:app", "--host", "0.0.0.0", "--port", "8420", "--workers", "2"]
