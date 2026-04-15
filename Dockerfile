FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN python3 -m venv . && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .

# Set environment variables for Vault authentication
ENV VAULT_URL=${VAULT_URL}
ENV VAULT_ROLE_ID=${VAULT_ROLE_ID}
ENV VAULT_SECRET_ID=${VAULT_SECRET_ID}

RUN . ./bin/activate
# Run the application
CMD ["python3", "main.py"]
