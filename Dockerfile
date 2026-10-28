FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OUTPUT_DIR=/tmp/market-river-generator

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY prompts ./prompts

RUN groupadd --gid 10001 worker \
    && useradd --uid 10001 --gid worker --create-home worker \
    && mkdir -p /tmp/market-river-generator \
    && chown worker:worker /tmp/market-river-generator

USER worker

CMD ["python", "-m", "app.main"]

