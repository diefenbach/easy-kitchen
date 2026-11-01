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

if grep -q 'image: registry.iqpp.de/iqpp/easykitchen:' docker-compose.yml; then
  sed -i 's|image: registry.iqpp.de/iqpp/easykitchen:[^[:space:]]*|image: ${EASYKITCHEN_IMAGE:-registry.iqpp.de/iqpp/easykitchen:0.7.0}|g' docker-compose.yml
fi

docker compose pull kitchen kitchen-mcp kitchen-static-init
docker compose up --no-deps kitchen-static-init
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
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=2)" \
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
