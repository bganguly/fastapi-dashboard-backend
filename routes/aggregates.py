from fastapi import APIRouter, Query
from db import get_conn

router = APIRouter()

@router.get("/api/aggregates")
def get_aggregates(
    from_: str = Query(alias="from"),
    to: str = Query(),
    topCategories: int = Query(default=5, ge=1, le=20),
    includeData: bool = True,
    includeTotal: bool = True,
):
    result: dict = {}

    if includeData:
        rows = _query_daily_summary_bucketed(from_, to, topCategories)
        result["data"] = _build_result(rows, topCategories)

    if includeTotal:
        count_sql = """
            SELECT COUNT(DISTINCT id) FROM orders
            WHERE "placedAt"::date BETWEEN %s::date AND %s::date
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(count_sql, [from_, to])
                result["totalOrders"] = cur.fetchone()[0]
        result["totalOrdersApproximate"] = False

    return result


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
