#!/bin/sh
# Runs ON THE SERVER as user `deploy`. The server's fixed /opt/dispel/deploy.sh wrapper updates the repo
# and then runs this file, so everything below ships through git (no server replacement needed).
set -eu
DIR="${DISPEL_DIR:-/opt/dispel}"
cd "$DIR"

# Public hostname: DOMAIN from .env if set, otherwise <ip-with-dashes>.sslip.io (valid TLS without owning a domain)
domain=$(sed -n 's/^DOMAIN=//p' .env)
ip=$(curl -fsS -m 5 http://169.254.169.254/v1/interfaces/0/ipv4/address)
host=${domain:-$(echo "$ip" | tr . -).sslip.io}
printf '%s {\n  reverse_proxy server:8765\n  request_body {\n    max_size 26MB\n  }\n}\n' "$host" > Caddyfile

# Refuse to run without the persistent volume: weights copied to the local disk would be wiped by a server replacement.
# The containers already running are left alone. Fix: check the volume is attached, then Actions -> infra -> replace_server.
if ! mountpoint -q "$DIR/models"; then
  echo "ERROR: $DIR/models is not the persistent models volume; not deploying" >&2
  exit 1
fi

docker compose -p dispel -f repo/docker/compose.prod.yml up -d --build
docker image prune -f > /dev/null
echo "deployed $(git -C repo rev-parse --short HEAD) at https://$host"
