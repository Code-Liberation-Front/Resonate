FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libopus0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persist the playlist database outside the container
ENV DB_PATH=/data/resonate.db
VOLUME /data

CMD ["python", "-m", "resonate"]
