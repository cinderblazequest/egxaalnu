# Используем минимальный python образ
FROM python:3.12-slim

WORKDIR /app

# Системные зависимости (минимум; ffmpeg оставлен для возможной генерации звука)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

CMD ["python", "-m", "bot"]
