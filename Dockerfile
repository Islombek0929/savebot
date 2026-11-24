FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 bot \
    && python -m venv /opt/venv \
    && chown -R bot:bot /opt/venv

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt && chown -R bot:bot /opt/venv

COPY savebot ./savebot
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh && mkdir -p /app/data && chown -R bot:bot /app

# Root emas, oddiy foydalanuvchi sifatida ishlaydi (xavfsizlik uchun)
USER bot
ENV DB_PATH=/app/data/bot.db
ENTRYPOINT ["docker-entrypoint.sh"]
