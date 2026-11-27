FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DATABASE_PATH=/data/history.db

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 1000 bot \
    && mkdir -p /data

COPY . .
RUN chown -R bot:bot /app /data

USER bot

CMD ["python", "main.py"]
