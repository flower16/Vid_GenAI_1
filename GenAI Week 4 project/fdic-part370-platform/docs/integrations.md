# External integrations & hosting

Every external service is **optional** — the platform runs fully locally without
any of them (RAG falls back to in-code rules, persistence to `audit_log.jsonl`,
auth to a local Admin principal). Configure the ones you want via env vars
(`.env` / Replit Secrets), then verify with the health check below.

## The five integrations

| Service | Purpose | Configure with | Configured when |
|---------|---------|----------------|-----------------|
| **LangSmith** | Tracing + offline eval experiments | `LANGSMITH_API_KEY`, `LANGSMITH_TRACING` | API key set |
| **Fireworks** | LLM-as-judge evals; fine-tune data | `FIREWORKS_API_KEY`, `FIREWORKS_JUDGE_MODEL` | API key set |
| **Snowflake** | Determination/audit persistence | `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PASSWORD`, … | account+user+password set |
| **Azure AD** | SSO login + RBAC (JWT validation) | `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, … (+ frontend `VITE_AZURE_*`) | tenant+client id set |
| **Pinecone** | RAG vector store for Part 370 rules | `PINECONE_API_KEY`, `PINECONE_INDEX` | API key set |

## Health check

One place answers "is X wired, and reachable right now?"
([core/integrations.py](../backend/app/core/integrations.py)).

**API** (used by the AppBar "Integrations N/5" chip):
```
GET /api/v1/health/integrations           # configured / not — cheap
GET /api/v1/health/integrations?live=true # also pings each configured service
```

**CLI:**
```bash
cd backend
python scripts/check_integrations.py         # configured summary
python scripts/check_integrations.py --live  # ping each configured service
python scripts/check_integrations.py --json
```

The live check is defensive — a missing key reports `configured=false`; an
unreachable service reports `reachable=false` with the reason, and never raises.
Live probes: LangSmith `list_datasets`, Fireworks `GET /models`, Snowflake
`SELECT 1`, Azure AD OIDC discovery document, Pinecone `list_indexes`.

Example (`--live`):
```
langsmith   ✓ reachable      project=fdic-part370, tracing=on; API reachable
fireworks   ✓ reachable      judge_model=…/glm-5p2; HTTP 200
snowflake   ✓ reachable      db=FDIC_PART370.CORE; SELECT 1 ok
azure_ad    · not configured tenant=common
pinecone    ✓ reachable      index=fdic-part370; index_present=True
```

> **Fireworks caveat.** The live check pings `/models`, which only proves the key
> and host are valid — **not** that `FIREWORKS_JUDGE_MODEL` itself is deployed. A
> retired/misspelled model id still shows `✓ reachable` here but 404s on the actual
> `/chat/completions` call, and the judges then log a warning and fall back to the
> free heuristic. Confirm the judge model resolves with a real call:
> `python scripts/run_fireworks_evals.py --json` and check `grader` is `fireworks`
> (not `heuristic`).

## Deploy on Replit

The repo ships Replit config so it runs as a **single web process**:

- [`.replit`](../.replit) — `run = "bash start.sh"`, Python 3.12 + Node 20 modules,
  port 8000 → public 80.
- [`replit.nix`](../replit.nix) — system packages.
- [`start.sh`](../start.sh) — installs backend deps, builds the frontend with
  `VITE_API_URL=""` (so the UI calls the API same-origin), then runs
  `uvicorn app.main:app` on `$PORT`.

FastAPI serves the built UI at `/` when `frontend/dist` exists
([main.py](../backend/app/main.py) `_mount_frontend`), while the API stays under
`/api/*` and `/health` (registered first, so they win over the static mount).
CORS also allows `*.repl.co` / `*.replit.dev` / `*.replit.app` origins.

**Replit setup:** create a Repl from this repo, add your keys in the **Secrets**
pane (`LANGSMITH_API_KEY`, `FIREWORKS_API_KEY`, `SNOWFLAKE_*`, `AZURE_*`,
`PINECONE_API_KEY`, and `VITE_AZURE_CLIENT_ID` for SSO), then press **Run**. With
no secrets it still boots in demo/local mode.
