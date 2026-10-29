# Dograh — Local Demo

This is the cloned **AGROSAHAS-PVT-LTD/dograh** fork running locally with Docker.

## Open

- **URL:** <http://localhost:3010>
- **API health:** <http://localhost:8000/api/v1/health>
- **MinIO console:** <http://localhost:9001>

## Demo login

- **Email:** `demo@dograh.dev`
- **Password:** `DograhDemo123!`

This account is stored only in the local PostgreSQL container.

## Running services

- `dograh-ui-1` — Next.js UI on port `3010`
- `dograh-api-1` — FastAPI backend on port `8000`
- `dograh-postgres-1` — PostgreSQL + pgvector on `5432`
- `dograh-redis-1` — Redis on `6379`
- `minio` — object storage on `9000` / console `9001`
- `dograh-cloudflared-stub` — local-only metrics stub; prevents the UI health check from waiting for a public tunnel

No Cloudflare tunnel is running and no public URL was created.

## Start / stop

```powershell
cd 'C:\Users\Admin\AppData\Local\Cline\Dograh'
docker compose up -d
docker start dograh-cloudflared-stub
```

```powershell
cd 'C:\Users\Admin\AppData\Local\Cline\Dograh'
docker compose down
docker stop dograh-cloudflared-stub
```

The local `.env` contains generated secrets and is intentionally not committed.

## SaaS mode

Use the overlay file so the local API/UI images expose the SaaS routes:

```powershell
cd 'C:\Users\Admin\AppData\Local\Cline\Dograh'
docker compose -f docker-compose.yaml -f docker-compose.saas.yaml up -d
```

SaaS pages:

- **Team:** <http://localhost:3010/team>
- **Plan & billing:** <http://localhost:3010/plan>
- **Accept invite:** <http://localhost:3010/invite?token=...>

### Flutterwave environment

Add these to `.env` and restart the API:

```dotenv
FLW_SECRET_KEY=FLWSECK-...
FLW_PUBLIC_KEY=FLWPUBK-...
FLW_WEBHOOK_SECRET=choose-a-long-random-secret
UI_APP_URL=http://localhost:3010
```

Configure the same `FLW_WEBHOOK_SECRET` in the Flutterwave dashboard's
**Settings → Webhooks** page, and set the webhook URL to:

```text
https://<your-public-api-host>/api/v1/saas/webhook/flutterwave
```

Local checkout stays disabled until `FLW_SECRET_KEY` is set. `FX_RATES_JSON`
can pin rates, for example `FX_RATES_JSON={"NGN":1650,"GHS":15.5}`.

