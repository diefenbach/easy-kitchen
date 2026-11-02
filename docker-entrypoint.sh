#!/bin/sh
set -eu

cd /app/src
python manage.py migrate --noinput
# --clear can briefly return 404s for assets while the shared static volume is repopulated.
python manage.py collectstatic --noinput --clear

if [ "${DJANGO_SUPERUSER_USERNAME:-}" ] && [ "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
  python manage.py createsuperuser --noinput || true
fi

exec "$@"
