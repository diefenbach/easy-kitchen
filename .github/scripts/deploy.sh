#!/bin/sh
set -eu

IMAGE="${1:?image is required}"
cd "${DEPLOY_PATH:?DEPLOY_PATH is required}"

if [ -f .env ] && grep -q '^EASYKITCHEN_IMAGE=' .env; then
  tmp="$(mktemp)"
  sed "s|^EASYKITCHEN_IMAGE=.*|EASYKITCHEN_IMAGE=${IMAGE}|" .env >"$tmp"
  mv "$tmp" .env
else
  printf '\nEASYKITCHEN_IMAGE=%s\n' "$IMAGE" >> .env
fi

docker compose pull kitchen kitchen-mcp
docker compose up -d postgres
docker compose run --rm --no-deps kitchen python manage.py migrate --noinput
docker compose run --rm --no-deps kitchen python manage.py collectstatic --noinput --clear
docker compose run --rm --no-deps kitchen sh -c '
  if [ "${DJANGO_SUPERUSER_USERNAME:-}" ] && [ "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
    python manage.py createsuperuser --noinput || true
  fi
'
docker compose up -d --no-deps kitchen kitchen-mcp
docker compose up -d --no-deps nginx

wait_for() {
  description="$1"
  shift
  i=0
  while [ "$i" -lt 60 ]; do
    if "$@"; then
      echo "$description is ready"
      return 0
    fi
    i=$((i + 1))
    sleep 2
  done
  echo "$description did not become ready" >&2
  return 1
}

kitchen_ready() {
  docker compose exec -T kitchen python -c \
    "import socket; socket.create_connection(('127.0.0.1', 8000), 2).close()" \
    >/dev/null 2>&1
}

mcp_ready() {
  docker compose exec -T kitchen-mcp python -c \
    "import socket; socket.create_connection(('127.0.0.1', 8001), 2).close()" \
    >/dev/null 2>&1
}

site_ready() {
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 https://kitchen.iqpp.de/)"
  case "$code" in
    2*|3*) return 0 ;;
    *) return 1 ;;
  esac
}

wait_for "kitchen" kitchen_ready
wait_for "kitchen-mcp" mcp_ready
wait_for "https://kitchen.iqpp.de/" site_ready
