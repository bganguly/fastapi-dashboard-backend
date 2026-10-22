# fastapi-dashboard-backend — FastAPI + Azure Container Apps

Production-grade **Python 3.12 / FastAPI** REST API delivering sub-second responses across
4 million orders: full-text search, pre-aggregated analytics tables, and serverless autoscaling
on Azure Container Apps. Serves the Angular 19 SPA deployed to Azure Static Web Apps.

---

## Live Service

| Endpoint | URL |
|---|---|
| **API Explorer** | https://salmon-wave-01f721c0f.6.azurestaticapps.net/api-explorer |
| **Dashboard** | https://salmon-wave-01f721c0f.6.azurestaticapps.net |
| **Portfolio demo** | https://bganguly.github.io/#angular_dashboard |

> Azure Container Apps scales to zero when idle; the first request after a period of inactivity may have a slight delay.

---

## Using the App

Open the **API Explorer** to run live requests against every endpoint from the browser.

1. **List orders** — `GET /api/orders` returns a paginated, date-sorted list of orders; response includes total row count and approximate flag.
2. **Full-text search** — `GET /api/orders?q=<term>` hits the GIN trigram index via ILIKE on the denormalized `search_text` column; sub-second on 4 M+ rows.
3. **Aggregates** — `GET /api/aggregates?from=<date>&to=<date>&topCategories=<n>` returns daily order totals and revenue by product category from the pre-aggregated `daily_summary` table.
4. **Customers** — `GET /api/customers` lists customers with cursor-based pagination; supports optional `q` and `regionId` filters.
5. **Regions** — `GET /api/regions` returns the distinct region list used by the filter sidebar in the frontend.

---

## Architecture

### Search & chart request flow — step by step

1. **Browser → Angular SPA** — the Angular 19 frontend sends `GET /api/orders?q=sara` directly to the FastAPI Container Apps service over HTTPS (no Nginx proxy — `apiBase` in `environment.prod.ts` points at the Container Apps FQDN).
2. **FastAPI → search** — `routes/orders.py` builds a parameterized `WHERE o.search_text ILIKE %s` query against PostgreSQL via the psycopg2 thread-safe connection pool; the GIN trigram index returns results in well under 1 s on 4 M+ rows.
3. **Chart path** — `GET /api/aggregates` is served entirely from the pre-aggregated `daily_summary` table; the handler never touches raw `orders` on the chart path.
4. **Count cap** — orders list enforces `COUNT_CAP = 10 000`; the capped subquery count avoids full sequential scans; the response includes an `approximate: true` flag when the real total exceeds the cap.
5. **Results → browser** — FastAPI returns paginated JSON; the Angular frontend renders the orders table, Highcharts stacked bar chart, and customers table.

```
Browser ──HTTPS──► Angular SPA (Azure SWA) ──HTTPS /api/*──► FastAPI (Container Apps) ──psycopg2──► PostgreSQL
                   CDN edge                                    scales to zero               4 M+ rows
                                                                                            GIN trigram index
```

### Topology

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           Azure Subscription                             │
│                                                                          │
│   Azure Static Web Apps                                                  │
│   ┌──────────────────────────────────────────────────────────────────┐  │
│   │  fastapi-angular-dashboard-frontend (SWA)                                         │  │
│   │  • Compiled Angular 19 SPA served from Azure CDN                 │  │
│   │  • Free tier — always-on, global edge                            │  │
│   └──────────────────────────────────────────────────────────────────┘  │
│                              │ HTTPS (/api/*)                            │
│   ┌──────────────────────────▼───────────────────────────────────────┐  │
│   │  Azure Container Apps: fastapi-dashboard-backend                 │  │
│   │  • FastAPI (Python 3.12) — uvicorn                               │  │
│   │  • ThreadedConnectionPool (psycopg2) — min 2, max 10 conns       │  │
│   │  • REST: /api/orders, /api/aggregates, /api/customers,           │  │
│   │          /api/regions                                            │  │
│   │  • 4 M+ orders, ILIKE on search_text, pre-agg daily_summary      │  │
│   │  • Scales to zero when idle; min-replicas 0, max-replicas 3      │  │
│   └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘

Deploy flow
───────────
local machine
  ├─ fastapi-dashboard-backend/scripts/deploy.sh  → Azure Container Apps (API)
  │    └─ prints BACKEND_URL → set in environment.prod.ts
  └─ fastapi-angular-dashboard-frontend/scripts/deploy.sh          → Azure SWA (frontend)
```

### Key design decisions

| Concern | Approach |
|---|---|
| **Search performance** | Denormalized `search_text` column (name + notes + total + id + status + region + date) with a GIN trigram index — sub-second ILIKE on 4 M rows, single index hit per token, no cross-table OR |
| **Count cap** | `COUNT_CAP = 10 000` capped subquery avoids full sequential scans on large result sets; response carries `approximate: true` when real total exceeds cap |
| **Chart performance** | Pre-aggregated `daily_summary` table — sub-second chart aggregates; handler never touches raw `orders` |
| **Top-N categories** | `/api/aggregates` ranks categories by total orders across the window and merges the tail into an "Others" bucket; `topCategories` query param (default 5) controls N |
| **Pagination** | Cursor-based (Customers via `c.id > %s`), offset (Orders); cursor approach avoids COUNT drift on concurrent writes |
| **Connection pool** | `psycopg2.pool.ThreadedConnectionPool` (min 2 / max 10) — shared across all uvicorn threads; pool initialised once at first request, reused for the process lifetime |
| **Status enum cast** | `o.status::text IN (...)` handles the PostgreSQL `OrderStatus` enum without requiring array cast notation |
| **Scale-to-zero** | Container Apps `--min-replicas 0` keeps cost at ~$0 when idle; first cold-start adds ~1–2 s latency |

---

## Stack

| Component | Implementation |
|---|---|
| **Python / FastAPI back-end** | Python 3.12, FastAPI 0.115, uvicorn, psycopg2-binary |
| **PostgreSQL — SQL, DML/DDL, performance tuning** | PostgreSQL 16; GIN trigram index on `search_text`; pre-aggregated `daily_summary` table for sub-second chart queries on 4 M rows |
| **Serverless / cloud-native computing** | Azure Container Apps — `az containerapp up --source .`; min-replicas: 0, max-replicas: 3, scales to zero |
| **CI/CD pipelines** | `deploy.sh` — `az containerapp up` remote source build + deploy; local uvicorn mode for development |
| **Secrets management** | `DATABASE_URL` passed as a Container Apps environment variable at deploy time; read from `.env` locally via python-dotenv |
| **RESTful APIs / microservices** | Four REST endpoints: orders (offset pagination + full-text search), aggregates (daily summary + Top-N categories), customers (cursor pagination), regions |
| **Performance optimization** | Sub-second ILIKE search on 4 M rows via GIN index; pre-aggregated daily tables cut chart query time from seconds to milliseconds; COUNT_CAP avoids full scans |
| **Frontend hosting** | Azure Static Web Apps — free tier CDN; Terraform provisions SWA resource and deploy token |
| **System design diagrams** | See architecture section above |

---

## Deployment / Running

```bash
./scripts/deploy.sh      # [1] local uvicorn :8000 · [2] Azure Container Apps
./scripts/infra-down.sh  # [1] kill :8000 · [2] destroy Azure stack
```

**Deploy the backend first** — the frontend `environment.prod.ts` must reference the Container Apps URL before the Angular build runs.

`./scripts/deploy.sh` prompts for local or Azure. The Azure remote flow:

| Step | What happens |
|---|---|
| **Check Azure access** | Verifies `az` CLI; runs `az login` if not authenticated |
| **Create resource group** | `az group create --name ${RG_NAME} --location ${AZ_LOCATION}` (idempotent) |
| **Build + deploy** | `az containerapp up --source . --target-port 8000` — remote source build in Azure Container Registry, deploys to Container Apps in one command |
| **Print backend URL** | Reads Container Apps FQDN and prints the `apiBase` value to set in `environment.prod.ts` |

After the backend URL is set in the frontend environment file:

```bash
cd ../fastapi-angular-dashboard-frontend
./scripts/deploy.sh      # [2] Azure SWA
```

---

## Scale & Performance

> **4 M+ orders** served with sub-second search and chart responses. Full-text search hits a GIN trigram index on `search_text`; chart aggregates hit pre-aggregated `daily_summary` — neither touches the raw `orders` table on the hot path.

```
Browser ──HTTPS──► Angular SPA (Azure SWA) ──HTTPS /api/*──► FastAPI (Container Apps) ──psycopg2──► PostgreSQL
                   CDN edge                                    scales to zero               4 M+ rows
                                                                                            GIN trigram index
```
