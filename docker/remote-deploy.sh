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

mountpoint -q "$DIR/models" || echo "WARNING: $DIR/models is not the persistent volume; weights placed here will NOT survive a server replacement"

docker compose -p dispel -f repo/docker/compose.prod.yml up -d --build
docker image prune -f > /dev/null
echo "deployed $(git -C repo rev-parse --short HEAD) at https://$host"
