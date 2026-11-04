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
        SELECT o."placedAt"::date::text AS day,
               cat.name AS category,
               COUNT(DISTINCT o.id) AS total_orders,
               COALESCE(SUM(oi.quantity * CAST(oi."unitPrice" AS FLOAT8) * (1 - CAST(oi.discount AS FLOAT8))), 0) AS total_revenue,
               COALESCE(SUM(oi.quantity), 0) AS total_items
        FROM orders o
        JOIN customers c ON c.id = o."customerId"
        JOIN regions r ON r.id = o."regionId"
        JOIN order_items oi ON oi."orderId" = o.id
        JOIN products p ON p.id = oi."productId"
        JOIN categories cat ON cat.id = p."categoryId"
        {where}
        GROUP BY o."placedAt"::date, cat.name
        ORDER BY o."placedAt"::date
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
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
