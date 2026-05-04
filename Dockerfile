# VERSION: 2.2.0 - Increment this for each release
# https://semver.org/

FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    sane \
    sane-utils \
    ocrmypdf \
    imagemagick \
    lsof \
    tesseract-ocr \
    unpaper \
    ghostscript \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV SCAN_DIRECTORY=/scans \
    ROOT_PATH=/ \
    VERSION=2.2.0 \
    DEBUG=False

RUN mkdir -p /scans /var/lock && \
    chmod -R 755 /scans

EXPOSE 5000

CMD ["python", "app.py"]