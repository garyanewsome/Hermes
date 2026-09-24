FROM node:20-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

WORKDIR /app

# ffmpeg: transcodes voice-memo uploads (browser MediaRecorder output —
# webm/opus or mp4/aac depending on browser) to the wav format Ollama's
# audio input actually accepts (confirmed live: it rejects webm outright).
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
# vite.config.js builds to ../static relative to /frontend, i.e. /static here.
COPY --from=frontend-build /static ./static/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
