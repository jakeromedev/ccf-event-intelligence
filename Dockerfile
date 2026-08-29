FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

RUN groupadd --system --gid 10001 ccf \
    && useradd --system --uid 10001 --gid ccf --home-dir /app ccf

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install --requirement requirements.txt

COPY . ./
RUN chmod 0755 /app/ops/docker-entrypoint.sh \
    && mkdir -p /app/instance /data/staged \
    && chown root:ccf /app/instance \
    && chmod 0750 /app/instance \
    && chown -R ccf:ccf /data

USER ccf
ENV CCF_ENV=production \
    CCF_STAGING_DIR=/data/staged

EXPOSE 8080
STOPSIGNAL SIGTERM

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8080')+'/health/live', timeout=3)"

ENTRYPOINT ["/app/ops/docker-entrypoint.sh"]
