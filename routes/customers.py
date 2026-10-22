from fastapi import APIRouter, Query
from typing import Optional
from db import get_conn

router = APIRouter()


@router.get("/api/customers")
def list_customers(
    cursor: Optional[int] = None,
    limit: int = Query(default=20, ge=1, le=100),
    q: Optional[str] = None,
    regionId: Optional[int] = None,
):
    limit = min(max(limit, 1), 100)
    clauses: list[str] = []
    params: list = []

    if cursor is not None:
        clauses.append('c.id > %s')
        params.append(cursor)
    if q and q.strip():
        clauses.append('(c."firstName" || \' \' || c."lastName" || \' \' || c.email) ILIKE %s')
        params.append(f"%{q.strip()}%")
    if regionId is not None:
        clauses.append('c."regionId" = %s')
        params.append(regionId)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit + 1)

    sql = f"""
        SELECT c.id, c.email, c."firstName", c."lastName", c.phone, c."createdAt",
               r.id AS r_id, r.code, r.name AS r_name
        FROM customers c
        JOIN regions r ON r.id = c."regionId"
        {where}
        ORDER BY c.id LIMIT %s
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]

    data = [
        {
            "id": r[0],
            "email": r[1],
            "firstName": r[2],
            "lastName": r[3],
            "phone": r[4],
            "createdAt": r[5].isoformat() if r[5] else None,
            "region": {"id": r[6], "code": r[7], "name": r[8]},
        }
        for r in rows
    ]

    next_cursor = data[-1]["id"] if has_more and data else None
    return {"data": data, "nextCursor": next_cursor, "hasMore": has_more}
