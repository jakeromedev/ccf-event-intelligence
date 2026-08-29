#!/bin/sh
set -eu

# Migrations are intentionally a separate deployment step. This check fails
# before serving traffic if configuration, MySQL, or schema compatibility is bad.
python -m flask --app 'app:create_app()' production-check

exec gunicorn --config /app/ops/gunicorn.conf.py 'app:create_app()'
