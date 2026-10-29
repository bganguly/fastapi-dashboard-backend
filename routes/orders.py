from fastapi import APIRouter, Query
from typing import Optional
from decimal import Decimal
from db import get_conn

router = APIRouter()

VALID_SORTS = {"placedAt", "total", "status", "customer", "id"}


@router.get("/api/orders")
def list_orders(
    q: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    sort: str = "placedAt",
    dir: str = "desc",
    status: Optional[str] = None,
    regionCode: Optional[str] = None,
    from_: Optional[str] = Query(default=None, alias="from"),
    to: Optional[str] = None,
    minTotal: Optional[Decimal] = None,
    maxTotal: Optional[Decimal] = None,
):
    page = max(page, 1)
    pageSize = min(max(pageSize, 1), 100)
    safe_sort = sort if sort in VALID_SORTS else "placedAt"
    safe_dir = "ASC" if dir.lower() == "asc" else "DESC"

    clauses: list[str] = []
    params: list = []

    if q and q.strip():
        clauses.append("o.search_text ILIKE %s")
        params.append(f"%{q.strip()}%")
    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if statuses:
            placeholders = ",".join(["%s"] * len(statuses))
            clauses.append(f"o.status::text IN ({placeholders})")
            params.extend(statuses)
    if regionCode:
        codes = [c.strip() for c in regionCode.split(",") if c.strip()]
        if codes:
            placeholders = ",".join(["%s"] * len(codes))
            clauses.append(f"r.code IN ({placeholders})")
            params.extend(codes)
    if from_:
        clauses.append('o."placedAt"::date >= %s::date')
        params.append(from_)
    if to:
        clauses.append('o."placedAt"::date <= %s::date')
        params.append(to)
    if minTotal is not None:
        clauses.append("o.total >= %s")
        params.append(minTotal)
    if maxTotal is not None:
        clauses.append("o.total <= %s")
        params.append(maxTotal)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    order_col = {
        "customer": f'c."firstName" {safe_dir}, c."lastName" {safe_dir}, o."placedAt" DESC',
        "total": f"o.total {safe_dir}, o.\"placedAt\" DESC",
        "status": f"o.status {safe_dir}, o.\"placedAt\" DESC",
        "id": f"o.id {safe_dir}",
    }.get(safe_sort, f'o."placedAt" {safe_dir}')

    count_sql = f"""
        SELECT COUNT(*)
        FROM orders o
        JOIN customers c ON c.id = o."customerId"
        JOIN regions r ON r.id = o."regionId"
        {where}
    """

    data_sql = f"""
        SELECT o.id, o.status, o.total, o.currency, o.notes, o."placedAt",
               c.id AS c_id, c.email, c."firstName", c."lastName", c.phone,
               r.id AS r_id, r.code AS r_code, r.name AS r_name
        FROM orders o
        JOIN customers c ON c.id = o."customerId"
        JOIN regions r ON r.id = o."regionId"
        {where}
        ORDER BY {order_col}
        LIMIT %s OFFSET %s
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(count_sql, params)
            raw_count = cur.fetchone()[0]
            cur.execute(data_sql, params + [pageSize, (page - 1) * pageSize])
            rows = cur.fetchall()

    approximate = False
    total = raw_count
    total_pages = max(1, -(-total // pageSize))

    data = [
        {
            "id": r[0],
            "status": r[1],
            "total": str(r[2]),
            "currency": r[3],
            "notes": r[4],
            "placedAt": r[5].isoformat() + "Z" if r[5] else None,
            "customer": {
                "id": r[6],
                "email": r[7],
                "firstName": r[8],
                "lastName": r[9],
                "phone": r[10],
            },
            "region": {"id": r[11], "code": r[12], "name": r[13]},
        }
        for r in rows
    ]

    return {
        "data": data,
        "page": page,
        "pageSize": pageSize,
        "total": total,
        "totalPages": total_pages,
        "approximate": approximate,
    }
