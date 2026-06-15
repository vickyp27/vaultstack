FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc build-essential libpq-dev qemu-utils \
    libguestfs-tools guestfs-tools \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/api

CMD ["celery", "-A", "celery_app", "worker", "--loglevel=info"]
