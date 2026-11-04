from fastapi import APIRouter, Query
from typing import Optional
from decimal import Decimal
from db import get_conn

router = APIRouter()


@router.get("/api/aggregates")
def get_aggregates(
    from_: str = Query(alias="from"),
    to: str = Query(),
    topCategories: int = Query(default=5, ge=1, le=20),
    includeData: bool = True,
    includeTotal: bool = True,
    q: Optional[str] = None,
    status: Optional[str] = None,
    regionCode: Optional[str] = None,
    minTotal: Optional[Decimal] = None,
    maxTotal: Optional[Decimal] = None,
):
    has_filters = bool(
        (q and q.strip())
        or status
        or regionCode
        or minTotal is not None
        or maxTotal is not None
    )

    result: dict = {}

    if includeData:
        if has_filters:
            rows = _query_orders_live(from_, to, topCategories, q, status, regionCode, minTotal, maxTotal)
        else:
            rows = _query_daily_summary_bucketed(from_, to, topCategories)
        result["data"] = _build_result(rows, topCategories)

    if includeTotal:
        clauses, params = _build_filter_clauses(from_, to, q, status, regionCode, minTotal, maxTotal)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        count_sql = f"""
            SELECT COUNT(*)
            FROM orders o
            JOIN customers c ON c.id = o."customerId"
            JOIN regions r ON r.id = o."regionId"
            {where}
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(count_sql, params)
                result["totalOrders"] = cur.fetchone()[0]
        result["totalOrdersApproximate"] = False

    return result


def _build_filter_clauses(from_: str, to: str, q, status, regionCode, minTotal, maxTotal):
    clauses: list[str] = []
    params: list = []

    clauses.append('o."placedAt"::date BETWEEN %s::date AND %s::date')
    params.extend([from_, to])

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
    if minTotal is not None:
        clauses.append("o.total >= %s")
        params.append(minTotal)
    if maxTotal is not None:
        clauses.append("o.total <= %s")
        params.append(maxTotal)

    return clauses, params


def _query_orders_live(from_: str, to: str, top_n: int, q, status, regionCode, minTotal, maxTotal) -> list:
    clauses, params = _build_filter_clauses(from_, to, q, status, regionCode, minTotal, maxTotal)
    where = "WHERE " + " AND ".join(clauses)

    sql = f"""
        WITH top_cats AS (
            SELECT o."categoryName"
            FROM orders o
            JOIN customers c ON c.id = o."customerId"
            JOIN regions r ON r.id = o."regionId"
            {where}
            GROUP BY o."categoryName"
            ORDER BY COUNT(*) DESC
            LIMIT %s
        )
        SELECT o."placedAt"::date::text AS day,
               CASE WHEN o."categoryName" IN (SELECT "categoryName" FROM top_cats)
                    THEN o."categoryName" ELSE 'Others' END AS category,
               COUNT(*) AS total_orders,
               SUM(o.total) AS total_revenue,
               0 AS total_items
        FROM orders o
        JOIN customers c ON c.id = o."customerId"
        JOIN regions r ON r.id = o."regionId"
        {where}
        GROUP BY day, category
        ORDER BY day
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params + [top_n] + params)
            return cur.fetchall()


def _query_daily_summary_bucketed(from_: str, to: str, top_n: int) -> list:
    sql = """
        WITH top_cats AS (
            SELECT "categoryName"
            FROM daily_summary
            WHERE date BETWEEN %s::date AND %s::date
            GROUP BY "categoryName"
            ORDER BY SUM("totalOrders") DESC
            LIMIT %s
        )
        SELECT date::text AS day,
               CASE WHEN "categoryName" IN (SELECT "categoryName" FROM top_cats)
                    THEN "categoryName" ELSE 'Others' END AS category,
               SUM("totalOrders")  AS total_orders,
               SUM("totalRevenue") AS total_revenue,
               SUM("totalItems")   AS total_items
        FROM daily_summary
        WHERE date BETWEEN %s::date AND %s::date
        GROUP BY date,
                 CASE WHEN "categoryName" IN (SELECT "categoryName" FROM top_cats)
                      THEN "categoryName" ELSE 'Others' END
        ORDER BY date
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, [from_, to, top_n, from_, to])
            return cur.fetchall()


def _build_result(rows: list, top_n: int) -> list:
    by_day: dict[str, dict] = {}
    day_order: list[str] = []

    for day, cat, total_orders, total_revenue, total_items in rows:
        if day not in by_day:
            by_day[day] = {}
            day_order.append(day)
        by_day[day][cat] = {
            "totalOrders": int(total_orders or 0),
            "totalRevenue": float(total_revenue or 0),
            "totalItems": int(total_items or 0),
        }

    result = []
    for day in day_order:
        cats: dict = {}
        others_entry = None
        for cat, vals in by_day[day].items():
            o, r, i = vals["totalOrders"], vals["totalRevenue"], vals["totalItems"]
            entry = {
                "totalOrders": o,
                "totalRevenue": r,
                "totalItems": i,
                "avgOrderValue": r / o if o > 0 else 0.0,
            }
            if cat == "Others":
                others_entry = entry
            else:
                cats[cat] = entry
        if others_entry is not None:
            cats["Others"] = others_entry
        result.append({"date": day, "categories": cats})

    return result
