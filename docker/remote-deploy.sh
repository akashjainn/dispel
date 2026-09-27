#!/bin/sh
# Runs ON THE SERVER as user `deploy`. The server's fixed /opt/dispel/deploy.sh wrapper updates the repo
# and then runs this file, so everything below ships through git (no server replacement needed).
set -eu
DIR="${DISPEL_DIR:-/opt/dispel}"
cd "$DIR"

# Public hostnames. <ip-with-dashes>.sslip.io always works (valid TLS without DNS; the deploy health check and older
# app configs use it). The domain (DOMAIN from .env, else hocuspocus.tech) is served on its apex, www and api once its
# DNS (Vultr zone, infra/vultr/dns.tf) points here; until then Caddy keeps retrying its certificates in the background.
domain=$(sed -n 's/^DOMAIN=//p' .env)
domain=${domain:-hocuspocus.tech}
ip=$(curl -fsS -m 5 http://169.254.169.254/v1/interfaces/0/ipv4/address)
host=$(echo "$ip" | tr . -).sslip.io
# The apex serves the website in web/ (www redirects to it); api and sslip.io reach the API server. The website reuses
# the desktop app's art, voice lines and sprite scripts straight from app/ (read-only mounts, see compose.prod.yml),
# and only its file check (POST /web/analyze, no key, limited per IP) and /health reach the server.
cat > Caddyfile <<EOF
www.$domain {
  redir https://$domain{uri} permanent
}
$domain {
  encode gzip
  header {
    X-Content-Type-Options nosniff
    Referrer-Policy no-referrer
  }
  handle /web/analyze {
    request_body {
      max_size 26MB
    }
    reverse_proxy server:8765
  }
  handle /health {
    reverse_proxy server:8765
  }
  handle_path /Assets/* {
    root * /srv/app/Assets
    file_server
  }
  @shared path /shared/sprites.js /shared/magic.js /shared/voice.js /shared/lessons.js
  handle @shared {
    uri strip_prefix /shared
    root * /srv/app/src/renderer
    file_server
  }
  handle {
    root * /srv/web
    file_server
  }
}
$host, api.$domain {
  reverse_proxy server:8765
  request_body {
    max_size 26MB
  }
}
EOF

# Refuse to run without the persistent volume: weights copied to the local disk would be wiped by a server replacement.
# The containers already running are left alone. Fix: check the volume is attached, then Actions -> infra -> replace_server.
if ! mountpoint -q "$DIR/models"; then
  echo "ERROR: $DIR/models is not the persistent models volume; not deploying" >&2
  exit 1
fi

docker compose -p dispel -f repo/docker/compose.prod.yml up -d --build
# Caddy doesn't watch its config, and `up` leaves an unchanged caddy container running: load the new site list (no downtime)
docker compose -p dispel -f repo/docker/compose.prod.yml exec -T caddy caddy reload --config /etc/caddy/Caddyfile
docker image prune -f > /dev/null
echo "deployed $(git -C repo rev-parse --short HEAD) at https://$host and https://api.$domain"
