#!/bin/sh
set -eu

cd /app/src
python manage.py migrate --noinput
python manage.py collectstatic --noinput

if [ "${DJANGO_SUPERUSER_USERNAME:-}" ] && [ "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
  python manage.py createsuperuser --noinput || true
fi

exec "$@"
