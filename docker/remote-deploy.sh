#!/bin/sh
# Runs ON THE SERVER as user `deploy`. The server's fixed /opt/dispel/deploy.sh wrapper updates the repo
# and then runs this file, so everything below ships through git (no server replacement needed).
#
# Settings can be pushed over stdin, one KEY=VALUE per line, from CI (see .github/workflows/deploy.yml).
# Only the keys listed in ALLOWED are accepted; they land in settings.env, which compose passes to the server.
set -eu
DIR="${DISPEL_DIR:-/opt/dispel}"
ALLOWED="GEMINI_API_KEY GEMINI_MODEL"
cd "$DIR"
umask 077
touch settings.env

if [ ! -t 0 ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    [ -n "$line" ] || continue
    key=${line%%=*}
    value=${line#*=}
    ok=""
    for a in $ALLOWED; do [ "$a" = "$key" ] && ok=1; done
    if [ -z "$ok" ]; then echo "ignored setting: $key"; continue; fi
    case "$value" in
      ""|*[!A-Za-z0-9_.:/-]*) echo "rejected $key: empty or unexpected characters"; exit 1 ;;
    esac
    { grep -v "^$key=" settings.env || true; echo "$key=$value"; } > settings.env.new
    mv settings.env.new settings.env
    echo "updated setting: $key"
  done
fi

[ -z "${SKIP_DOCKER:-}" ] || exit 0

# Public hostname: DOMAIN from .env if set, otherwise <ip-with-dashes>.sslip.io (valid TLS without owning a domain)
domain=$(sed -n 's/^DOMAIN=//p' .env)
ip=$(curl -fsS -m 5 http://169.254.169.254/v1/interfaces/0/ipv4/address)
host=${domain:-$(echo "$ip" | tr . -).sslip.io}
printf '%s {\n  reverse_proxy server:8765\n  request_body {\n    max_size 26MB\n  }\n}\n' "$host" > Caddyfile

mountpoint -q "$DIR/models" || echo "WARNING: $DIR/models is not the persistent volume; weights placed here will NOT survive a server replacement"

docker compose -p dispel -f repo/docker/compose.prod.yml up -d --build
docker image prune -f > /dev/null
echo "deployed $(git -C repo rev-parse --short HEAD) at https://$host"
