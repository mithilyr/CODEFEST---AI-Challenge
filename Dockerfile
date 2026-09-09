# Ashen Era Archive Assistant.
#
# The archive itself (~123 MB) is not baked into the image - it's downloaded
# on first container start by docker-entrypoint.sh, straight into data/,
# which should be a mounted volume so it survives container restarts and
# `docker compose down`.
FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x docker-entrypoint.sh

# Archive lives here; mount a volume at this path to avoid re-downloading it
# every time the container is recreated.
VOLUME ["/app/data"]

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["python", "-m", "src.ui.server", "--host", "0.0.0.0", "--port", "8000"]
