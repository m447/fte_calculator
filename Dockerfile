FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app_v2/ ./app_v2/
COPY app/static/ ./app/static/

# Copy models and data
COPY models/ ./models/
COPY data/ml_ready_v3.csv ./data/
COPY data/gross_factors.json ./data/
COPY data/revenue_monthly.csv ./data/
COPY data/revenue_annual.csv ./data/

# Expose port
ENV PORT=8080
EXPOSE 8080

# Run with gunicorn
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 120 app_v2.server:app
