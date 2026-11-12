# One container runs the bot for every repo the GitHub App is installed on.
# Build:  docker build -t tidebot .
# Run:    docker run --env-file .env -v tidebot-data:/data \
#           -v "$PWD/app.pem:/run/secrets/app.pem:ro" -p 8000:8000 tidebot
# with TIDEBOT_PRIVATE_KEY=/run/secrets/app.pem in .env (see .env.example).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TIDEBOT_STATE=/data/state.json

WORKDIR /app
COPY pyproject.toml README.md ./
COPY tidebot ./tidebot
RUN pip install --no-cache-dir ".[serve]"

RUN useradd --system --uid 10001 --home-dir /data tidebot \
    && mkdir -p /data && chown tidebot /data
USER tidebot
VOLUME /data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"]
CMD ["uvicorn", "tidebot.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
