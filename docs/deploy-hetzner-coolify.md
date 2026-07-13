# Deploy to Hetzner + Coolify

Full production deployment of Email Hub on a Hetzner VPS with Coolify. Single server runs everything: Next.js frontend, FastAPI backend, PostgreSQL, Redis, Maizzle sidecar, and nginx reverse proxy.

**Cost:** ~€4.50/mo (Hetzner CX22) + €0 (Coolify is free/open-source)

## Prerequisites

- A Hetzner Cloud account ([accounts.hetzner.com](https://accounts.hetzner.com))
- A domain name (optional but recommended for SSL)
- Your GitHub repo: `linardsb/email-hub`
- An Anthropic API key for the AI agent pipeline

---

## Step 1: Create Hetzner VPS

1. Log in to [console.hetzner.cloud](https://console.hetzner.cloud)
2. Click **Add Server**
3. Configure:
   - **Location:** Choose nearest to your users (e.g., Helsinki for EU)
   - **Image:** Ubuntu 24.04
   - **Type:** CX22 (2 vCPU, 4GB RAM, 40GB disk) — €4.50/mo
   - **Networking:** Enable public IPv4
   - **SSH Key:** Add your SSH public key (or create one: `ssh-keygen -t ed25519`)
   - **Volume:** Add a 20GB volume for database persistence (€1.04/mo) — optional but recommended
   - **Name:** `email-hub`
4. Click **Create & Buy Now**
5. Note the server IP address (e.g., `65.109.xx.xx`)

### Optional: Add DNS

If you have a domain, add an A record:
```
email-hub.yourdomain.com → 65.109.xx.xx
```

---

## Step 2: Install Coolify

SSH into your server and run the one-line installer:

```bash
ssh root@65.109.xx.xx

# Install Coolify
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash
```

This takes ~5 minutes. When done:

1. Open `http://65.109.xx.xx:8000` in your browser
2. Create your admin account
3. Coolify dashboard is ready

---

## Step 3: Connect GitHub

1. In Coolify dashboard → **Sources** → **Add GitHub App**
2. Follow the OAuth flow to connect your GitHub account
3. Grant access to `linardsb/email-hub`

---

## Step 4: Create the Project

1. **Projects** → **Add New Project** → name it "Email Hub"
2. Click into the project → **Add New Resource**
3. Select **Docker Compose** → **GitHub Repository**
4. Select `linardsb/email-hub` → branch `main`
5. Coolify detects `docker-compose.yml` automatically

---

## Step 5: Configure Environment Variables

In Coolify, go to your resource → **Environment Variables** and add:

### Required

```env
# Database (Coolify connects these automatically via docker network)
POSTGRES_USER=emailhub
POSTGRES_PASSWORD=<generate: openssl rand -base64 24>
POSTGRES_DB=email_hub

# Redis
REDIS_PASSWORD=<generate: openssl rand -base64 24>

# Auth
AUTH_SECRET=<generate: openssl rand -base64 32>
AUTH__JWT_SECRET_KEY=<generate: openssl rand -base64 32>
AUTH__DEMO_USER_PASSWORD=<your admin password>

# AI Provider (required for Scaffolder agent)
AI__PROVIDER=anthropic
AI__API_KEY=sk-ant-api03-...
AI__MODEL=claude-sonnet-4-20250514

# Environment
ENVIRONMENT=production
LOG_LEVEL=INFO
```

### Optional

```env
# Figma (default PAT — users can also provide their own per-connection)
DESIGN_SYNC__FIGMA_PAT=figd_...

# Embedding (for knowledge/vector search)
EMBEDDING__PROVIDER=openai
EMBEDDING__API_KEY=sk-...

# Custom encryption key for design sync tokens (falls back to JWT secret)
DESIGN_SYNC__ENCRYPTION_KEY=<generate: openssl rand -base64 32>
```

---

## Step 6: Configure Domain & SSL

1. In Coolify → your resource → **Settings**
2. Set the domain: `email-hub.yourdomain.com` (or use the Coolify-provided URL)
3. Enable **SSL** — Coolify auto-provisions Let's Encrypt certificates
4. Set the **Exposed Port** to the nginx service port (80)

The nginx service in your docker-compose handles internal routing:
- `/` → Next.js frontend (port 3000)
- `/api/` → FastAPI backend (port 8891)
- `/health` → health check

---

## Step 7: Deploy

1. Click **Deploy** in Coolify
2. Coolify builds all containers from your `docker-compose.yml`
3. Watch the build logs — first deploy takes ~5-10 minutes
4. Once all services are green, the app is live

### Verify

```bash
# Health check
curl https://email-hub.yourdomain.com/health

# Backend API
curl https://email-hub.yourdomain.com/api/v1/components/
```

---

## Step 8: Seed the Database

The first deploy creates empty tables (via the `migrate` service). You need to seed the admin user and components.

In Coolify → your `app` service → **Terminal** (or SSH into the server):

```bash
# Find the running app container
docker ps | grep email-hub.*app

# Run the seed script
docker exec -it <container_id> python -m app.seed_demo
```

This creates:
- Admin user (`admin@email-hub.dev` + your configured password)
- Sample client org and project
- 21 email components (header, hero, footer, columns, CTA, etc.)

### Verify seeding

```bash
curl https://email-hub.yourdomain.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@email-hub.dev","password":"<your password>"}'
```

You should get back a JSON response with `access_token`.

---

## Step 9: Update Frontend Environment

The Next.js frontend inside the docker-compose already has the right env vars set in `docker-compose.yml`:

```yaml
environment:
  - INTERNAL_API_URL=http://app:8891
  - AUTH_SECRET=${AUTH_SECRET}
  - AUTH_TRUST_HOST=true
```

If you're keeping Vercel as well, update Vercel env vars:
```
BACKEND_URL=https://email-hub.yourdomain.com
AUTH_SECRET=<same value as above>
AUTH_TRUST_HOST=true
```

---

## Ongoing Operations

### Auto-deploy on push

Coolify can auto-deploy when you push to `main`:
1. Resource → **Webhooks** → copy the webhook URL
2. GitHub → repo **Settings** → **Webhooks** → add the URL
3. Set to trigger on `push` events to `main`

### Database backups

```bash
# SSH into server
ssh root@65.109.xx.xx

# Backup PostgreSQL
docker exec $(docker ps -q -f name=db) pg_dump -U emailhub email_hub > backup_$(date +%Y%m%d).sql

# Restore
cat backup_20260320.sql | docker exec -i $(docker ps -q -f name=db) psql -U emailhub email_hub
```

For automated backups, Coolify has built-in scheduled backup support — configure in **Settings** → **Backups**.

### If using a Hetzner Volume for DB persistence

```bash
# Mount the volume (Hetzner attaches it at /mnt/HC_Volume_xxxxx)
# Update docker-compose.yml volumes:
# postgres_data: /mnt/HC_Volume_xxxxx/postgres
```

### Monitoring

Coolify shows container logs, CPU, and memory usage in the dashboard. For more:

```bash
# View logs
docker compose logs -f app    # Backend logs
docker compose logs -f cms    # Frontend logs
docker compose logs -f db     # Database logs
```

### Scaling up

If you outgrow CX22:
- **CX32** (4 vCPU, 8GB) — €7.20/mo
- **CX42** (8 vCPU, 16GB) — €14.40/mo

Resize in Hetzner console with ~30 seconds downtime.

---

## Security Checklist

- [x] SSH key auth only (disable password auth in `/etc/ssh/sshd_config`)
- [x] SSL via Let's Encrypt (auto-provisioned by Coolify)
- [x] Database not exposed publicly (only accessible via docker network)
- [x] Redis password-protected
- [x] API keys in Coolify env vars (not in code)
- [x] Nginx with security headers (X-Frame-Options, CSP, HSTS)
- [ ] Enable Hetzner Firewall: allow only ports 22 (SSH), 80 (HTTP), 443 (HTTPS)
- [ ] Set up fail2ban: `apt install fail2ban`
- [ ] Enable automatic security updates: `apt install unattended-upgrades`

### Hetzner Firewall Rules

In Hetzner console → **Firewalls** → create:

| Direction | Protocol | Port | Source |
|-----------|----------|------|--------|
| Inbound | TCP | 22 | Your IP only |
| Inbound | TCP | 80 | Any |
| Inbound | TCP | 443 | Any |
| Inbound | TCP | 8000 | Your IP only (Coolify dashboard) |

Apply the firewall to your server.

---

## Cost Summary

| Resource | Monthly Cost |
|----------|-------------|
| Hetzner CX22 (2 vCPU, 4GB RAM) | €4.50 |
| Hetzner Volume 20GB (optional) | €1.04 |
| Coolify | Free |
| Let's Encrypt SSL | Free |
| **Total** | **€4.50 - €5.54/mo** |

Plus API costs:
- Anthropic (Scaffolder agent): ~$0.04 per email generation
- OpenAI embeddings (optional): ~$0.001 per query
