import os
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import orders, aggregates, customers, regions

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
