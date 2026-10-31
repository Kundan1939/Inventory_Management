# SSL/TLS Certificates Directory

This directory is mounted to `/app/certs` inside the container.

### Option 1: Native HTTPS via Gunicorn
Place your valid SSL certificates here named:
- `cert.pem` (or fullchain.pem)
- `key.pem` (or privkey.pem)

When both files are present, `docker-entrypoint.sh` will automatically detect them and start Gunicorn with native HTTPS encryption on port 5000 / 443!

### Option 2: Production Reverse Proxy (Recommended)
If you run behind Nginx, Caddy, Traefik, or Cloudflare:
- Terminate SSL at the reverse proxy.
- Ensure the reverse proxy forwards `X-Forwarded-Proto: https` and `X-Forwarded-For: $remote_addr`.
- Direct unencrypted access to `http://<public-ip>:5000` is blocked with `403 Forbidden` automatically!
- Local LAN access (e.g. `http://192.168.x.x:5000` or `http://127.0.0.1:5000`) is allowed.
