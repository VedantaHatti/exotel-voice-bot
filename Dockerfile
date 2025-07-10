# Simple Dockerfile for Exotel Voice Bot
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy all files
COPY . .

# Install dependencies
RUN pip install fastapi uvicorn websockets pydantic python-dotenv loguru requests pipecat-ai numpy soundfile openai deepgram-sdk

# Expose port
EXPOSE 8765

# Run the app
CMD ["python", "server.py"]