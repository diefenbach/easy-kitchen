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

curl -fsS -o /dev/null --retry 8 --retry-delay 3 --retry-all-errors https://kitchen.iqpp.de/
