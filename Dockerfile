# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies (libpq for psycopg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install Python dependencies
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Download Tailwind CSS standalone CLI and compile CSS
# (safety net: rebuild even though main.css is committed to git)
ADD https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64 /usr/local/bin/tailwindcss
RUN chmod +x /usr/local/bin/tailwindcss

# Copy application code
COPY . .

# Rebuild Tailwind CSS (ensures Docker image has fresh CSS)
RUN tailwindcss -i static/css/input.css -o static/css/main.css --minify

# Collect static files
RUN DJANGO_SETTINGS_MODULE=boot.settings \
    DJANGO_CONFIGURATION=Production \
    DJANGO_SECRET_KEY=build-time-secret \
    python manage.py collectstatic --noinput --ignore "input.css"

# Make entrypoint and CLI scripts executable
RUN chmod +x docker-entrypoint.sh doorito

# Create non-root user
RUN addgroup --system --gid 1001 django \
    && adduser --system --uid 1001 --gid 1001 django \
    && chown -R django:django /app

USER django

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["web"]
