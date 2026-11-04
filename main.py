import os
import threading
import datetime
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import orders, aggregates, customers, regions, dataset_bounds
from db import get_conn

app = FastAPI(title="Angular Dashboard API", docs_url="/docs", redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(orders.router)
app.include_router(aggregates.router)
app.include_router(customers.router)
app.include_router(regions.router)
app.include_router(dataset_bounds.router)


def _warmup_count_cache():
    try:
        default_from = "2020-01-01"
        default_to = datetime.date.today().isoformat()
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'WITH recent AS ('
                    '  SELECT c."firstName", c."lastName"'
                    '  FROM orders o JOIN customers c ON c.id = o."customerId"'
                    '  ORDER BY o."placedAt" DESC LIMIT 40'
                    ') SELECT DISTINCT "firstName", "lastName" FROM recent'
                )
                rows = cur.fetchall()
                tokens = set()
                for first, last in rows:
                    if first and first.strip():
                        tokens.add(first.strip().lower())
                    if last and last.strip():
                        tokens.add(last.strip().lower())

                for token in tokens:
                    key = (
                        f"q={token}&status=&regionCode="
                        f"&from={default_from}&to={default_to}"
                        f"&minTotal=&maxTotal="
                    )
                    cur.execute(
                        "SELECT 1 FROM count_cache WHERE cache_key = %s"
                        " AND cached_at > NOW() - INTERVAL '30 days'",
                        [key],
                    )
                    if cur.fetchone():
                        continue
                    cur.execute(
                        "SELECT COUNT(*) FROM orders o"
                        ' WHERE o."placedAt" >= %s::timestamptz'
                        ' AND o."placedAt" <= (%s::date + interval \'1 day\' - interval \'1 second\')'
                        " AND o.search_text ILIKE %s",
                        [default_from, default_to, f"%{token}%"],
                    )
                    count = cur.fetchone()[0]
                    cur.execute(
                        "INSERT INTO count_cache (cache_key, total, cached_at) VALUES (%s, %s, NOW())"
                        " ON CONFLICT (cache_key) DO UPDATE SET total = %s, cached_at = NOW()",
                        [key, count, count],
                    )
    except Exception:
        pass


@app.on_event("startup")
def startup_warmup():
    threading.Thread(target=_warmup_count_cache, daemon=True, name="count-cache-warmup").start()


@app.get("/health")
def health():
    return {"status": "ok"}



@app.get("/")
def root():
    return {
        "service": "Angular Dashboard API",
        "runtime": "FastAPI · Python 3.12",
        "endpoints": {
            "GET /api/orders": "paginated list — ?q=&page=&pageSize=&sort=&dir=&status=&regionCode=&from=&to=",
            "GET /api/aggregates": "daily totals by category — ?from=&to=&topCategories=",
            "GET /api/customers": "cursor-paginated list — ?cursor=&limit=&q=",
            "GET /api/regions": "all regions",
        },
    }
