# Use official Python image
FROM python:3.12-slim
# Set workdir inside container
WORKDIR /app
# Copy requirements and install dependencies
COPY requirements.txt .
COPY .env .env
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt
# Copy application code
COPY app/ ./app
# Expose port for FastAPI
EXPOSE 8081
# Set environment variables (optional)
ENV PYTHONUNBUFFERED=1
# Start the FastAPI server with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8081"]
