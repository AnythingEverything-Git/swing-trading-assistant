# Release plan — promote local → AWS (personal live)

AWS Free Tier EC2 is **production** (Upstox live, no demo). Local is **dev** (demo).  
Env details: [ENVIRONMENTS.md](./ENVIRONMENTS.md) · Smoke detail: [RELEASE_SMOKE.md](./RELEASE_SMOKE.md)

## Milestones

| ID | Gate | Exit criteria |
|----|------|----------------|
| **M0** | Env split + app on AWS | Prod live-only; sync recipe works; Free Tier intact |
| **M1** | Local green | Change works on demo locally; unit tests for touched areas |
| **M2** | AWS live platform | `live_ready=true`, candles present, cron/token OK |
| **M3** | Promote build | Sync → `compose build/up` → alembic → status still Live |
| **M4** | Release smoke | EIP UI + checklist below; then UI back to localhost |

Intraday multi-year certification, auth, and billing are **out of scope** for this personal release train.

## Promote recipe (M3)

On laptop (from repo root), sync **without** local `.env`:

```powershell
$pem = "C:\Users\User\Downloads\AWSec2\ec2KeyPair.pem"
$remote = "ubuntu@13.235.110.243"
scp -i $pem Dockerfile docker-compose.yml alembic.ini .dockerignore "${remote}:/opt/tradepilot/"
scp -i $pem -r backend ops "${remote}:/opt/tradepilot/"
```

On VPS:

```bash
cd /opt/tradepilot
sed -i 's/\r$//' ops/vps/*.sh
chmod +x ops/vps/*.sh
docker compose build
docker compose up -d
docker compose exec -w /app api python -m alembic -c alembic.ini upgrade head
curl -s http://127.0.0.1:8001/api/v1/product/status
```

Never overwrite `/opt/tradepilot/.env` with laptop demo settings.

## Release smoke (M4) — Free Tier

Point a browser at **http://13.235.110.243/** (hosted UI). Prefer **Nifty 50** (NSE_ALL scans thrash `t3.micro`).

1. Banner **Live** Upstox; product status `production` / `upstox` / `live_ready=true`  
2. Find setups (Nifty 50) completes  
3. Inspect / chart for one liquid name  
4. Intraday morning board (1m coverage permitting)  
5. Optional: brief send if SES configured  
6. Confirm instance still `t3.micro`, disk ≤ 30 GB  

**Sign-off:** ________ date ________  

Then restore UI to `http://127.0.0.1:8001` for coding.
