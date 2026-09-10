# Environments — local (dev) vs AWS (production live)

| | **Local (dev)** | **AWS (production / release)** |
|--|-----------------|--------------------------------|
| Purpose | Coding, UI, experiments | Always-on live TradePilot |
| Host | Your PC | EC2 Free Tier `tradepilot-live` |
| API | `http://127.0.0.1:8001` | `http://13.235.110.243:8001` (also via UI `/api`) |
| **UI** | Vite `http://127.0.0.1:5173` | **`http://13.235.110.243/`** (nginx on EC2) |
| DB | Local Postgres / Compose | Docker Postgres on EC2 only |
| `ENVIRONMENT` | `development` | `production` |
| Market data | **`demo`** | **`upstox` only — never demo** |
| UI default | `frontend/.env.development` → localhost | Copy `.env.production.local.example` only for release smoke |

Startup refuses `ENVIRONMENT=production` + `MARKET_DATA_SOURCE=demo`.  
Development refuses a remote `DATABASE_URL` host (blocks pointing local API at AWS DB).

## Start local (dev)

```powershell
# Postgres (native or):
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres

cd backend
python run_api.py --host 127.0.0.1 --port 8001

cd frontend
npm run dev
```

Banner should say **Demo**. Network tab → `127.0.0.1:8001`.

## Use AWS (production)

**Prod UI (browser):** [http://13.235.110.243/](http://13.235.110.243/)

Infra: [AWS_INFRA.md](./AWS_INFRA.md) · VPS ops: [ops/vps/README.md](../ops/vps/README.md) · Release train: [RELEASE_PLAN.md](./RELEASE_PLAN.md)

## Forbidden

- Copying laptop `.env` (demo) onto the VPS  
- Copying VPS `.env` into daily local `.env`  
- Setting local `DATABASE_URL` to the EIP (tunnel is inspect-only)  
- `MARKET_DATA_SOURCE=demo` on AWS  
