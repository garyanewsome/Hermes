FROM node:20-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

WORKDIR /app

# ffmpeg: transcodes voice-memo/song uploads (browser MediaRecorder
# output — webm/opus or mp4/aac depending on browser) to the wav format
# Ollama's audio input and the chord/melody analysis libraries actually
# accept (confirmed live: Ollama rejects webm outright). libsndfile1:
# native dependency of librosa/soundfile (chord/melody analysis).
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# basic-pitch (melody/riff transcription) pinned via --no-deps as a
# SEPARATE install, after requirements.txt already provided its real
# runtime deps above: its own declared dependency list hard-pins
# tensorflow<2.15.1 for Python>=3.11, and no such tensorflow build exists
# for Python 3.12 on Linux — confirmed live, pip's resolver fails outright
# otherwise. It runs fine on the onnxruntime backend instead (falls back
# with just a warning when tensorflow/coreml/tflite aren't installed).
RUN pip install --no-cache-dir --no-deps basic-pitch==0.4.0

COPY app/ ./app/
# vite.config.js builds to ../static relative to /frontend, i.e. /static here.
COPY --from=frontend-build /static ./static/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
