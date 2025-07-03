FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

# Set working directory
WORKDIR /app

# Copy and install Python dependencies as root, then change ownership
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code as root
COPY *.py ./
COPY system_prompt.md ./

# Give ownership of everything to appuser
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose the port
EXPOSE 5000

# Set default environment variables (can be overridden)
ENV FLASK_HOST=0.0.0.0 \
    FLASK_PORT=5000 \
    DATA_DIR=/app

# Run the application
CMD ["python", "app.py"]